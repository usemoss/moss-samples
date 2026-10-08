"""Engine adapters: every engine indexes unit-norm float32 vectors and ranks by inner product (= cosine).

Contract (used by run.py), identical for all engines:
  name: str              short identifier written into result files
  sweep: list[dict]      search-parameter settings swept in the serial stage ([] = exact engine, one point)
  build(ids, vectors, metadata) -> None     index all docs (ids int64, vectors (n, d) float32, metadata or None)
  set_search(params) -> None                apply one sweep setting
  search(q, k, flt) -> list[int]            top-k doc ids for one query vector; flt is a neutral filter or None
  close() -> None                           free resources
Moss's build/search/close are coroutines (its public API is async); the other engines are synchronous.

A neutral filter is {"field": "id", "op": "gte", "value": int} or {"field": "labels", "op": "eq", "value": str}.
Metadata rows are {"id": int, "labels": str}.
"""

import shutil
import sqlite3
import tempfile
import threading
import uuid
from pathlib import Path

import numpy as np

HNSW_M, HNSW_EF_CONSTRUCTION = 16, 200
EF_SWEEP = [{"ef": e} for e in (16, 32, 64, 128, 256, 512)]
BATCH = 1000


def _sql_op(flt: dict) -> str:
    """SQL comparison operator for a neutral filter."""
    return ">=" if flt["op"] == "gte" else "="


class MossEngine:
    """Moss through its public Python API: one uniquely named SessionIndex with custom vectors, never pushed."""

    name, sweep = "moss", []

    def __init__(self) -> None:
        """Create the engine; the session opens in build()."""
        self.session = None

    async def build(
        self, ids: np.ndarray, vectors: np.ndarray, metadata: list[dict] | None
    ) -> None:
        """Open a custom-embedding session and add docs in batches of BATCH (keeps Python lists small)."""
        import os

        from dotenv import load_dotenv
        from moss import DocumentInfo, MossClient

        if "MOSS_ENV_FILE" in os.environ:
            load_dotenv(os.environ["MOSS_ENV_FILE"], override=True)
        client = MossClient(
            os.environ["MOSS_PROJECT_ID"], os.environ["MOSS_PROJECT_KEY"]
        )
        self.session = await client.session(
            f"bench-{uuid.uuid4().hex[:8]}", model_id="custom"
        )
        for i in range(0, len(ids), BATCH):
            docs = [
                DocumentInfo(
                    id=str(ids[i + j]),
                    text="",
                    embedding=row,
                    metadata={k: str(v) for k, v in metadata[i + j].items()}
                    if metadata
                    else None,
                )
                for j, row in enumerate(vectors[i : i + BATCH].tolist())
            ]
            await self.session.add_docs(docs)

    def set_search(self, params: dict) -> None:
        """Moss has no search parameters (exact search)."""

    async def search(self, q: np.ndarray, k: int, flt: dict | None = None) -> list[int]:
        """Vector-only query (alpha=1.0); filters use Moss's string-valued, numeric-aware operators."""
        from moss import QueryOptions

        f = (
            {"field": flt["field"], "condition": {f"${flt['op']}": str(flt["value"])}}
            if flt
            else None
        )
        r = await self.session.query(
            "", QueryOptions(top_k=k, alpha=1.0, embedding=q.tolist(), filter=f)
        )
        return [int(d.id) for d in r.docs]

    async def close(self) -> None:
        """Send Moss's final telemetry and free the session."""
        await self.session.close()


class ChromaEngine:
    """Chroma in-process (PersistentClient in a temp dir) with its HNSW index in inner-product space.

    A persistent client is required for the ef sweep: chromadb 1.5.9 stores a modified ef_search but the loaded
    index keeps the old value until the client is reopened (verified: recall unchanged on EphemeralClient).
    """

    name, sweep = "chroma", EF_SWEEP

    def build(
        self, ids: np.ndarray, vectors: np.ndarray, metadata: list[dict] | None
    ) -> None:
        """Create an ip-space collection (M, ef_construction fixed) and add docs in the client's max batch size."""
        import chromadb
        from chromadb.config import Settings

        self.dir = Path(tempfile.mkdtemp(prefix="bench-chroma-"))
        client = chromadb.PersistentClient(str(self.dir), Settings(anonymized_telemetry=False))
        self.col = client.create_collection(
            "bench",
            configuration={
                "hnsw": {
                    "space": "ip",
                    "max_neighbors": HNSW_M,
                    "ef_construction": HNSW_EF_CONSTRUCTION,
                }
            },
        )
        step = client.get_max_batch_size()
        for i in range(0, len(ids), step):
            self.col.add(
                ids=[str(x) for x in ids[i : i + step]],
                embeddings=vectors[i : i + step],
                metadatas=metadata[i : i + step] if metadata else None,
            )

    def set_search(self, params: dict) -> None:
        """Set HNSW ef_search, then reopen the client so the loaded index uses it."""
        import chromadb
        from chromadb.config import Settings

        settings = Settings(anonymized_telemetry=False)
        self.col.modify(configuration={"hnsw": {"ef_search": params["ef"]}})
        chromadb.PersistentClient(str(self.dir), settings).clear_system_cache()
        self.col = chromadb.PersistentClient(str(self.dir), settings).get_collection("bench")

    def search(self, q: np.ndarray, k: int, flt: dict | None = None) -> list[int]:
        """Query by embedding; neutral filters map to Chroma's where clause ($gte / $eq)."""
        where = {flt["field"]: {f"${flt['op']}": flt["value"]}} if flt else None
        return [
            int(x)
            for x in self.col.query(query_embeddings=[q], n_results=k, where=where)[
                "ids"
            ][0]
        ]

    def close(self) -> None:
        """Delete the temp database directory."""
        shutil.rmtree(self.dir, ignore_errors=True)


class LanceEngine:
    """LanceDB embedded, HNSW-SQ index (one partition), dot distance; filters are prefiltered where clauses."""

    name, sweep = "lancedb", EF_SWEEP

    def build(
        self, ids: np.ndarray, vectors: np.ndarray, metadata: list[dict] | None
    ) -> None:
        """Write a Lance table in a temp dir (batches of 100k rows), then build the HnswSq index."""
        import lancedb
        import pyarrow as pa
        from lancedb.index import HnswSq

        self.dir = Path(tempfile.mkdtemp(prefix="bench-lancedb-"))
        db, d, self.table = lancedb.connect(self.dir), vectors.shape[1], None
        for i in range(0, len(ids), 100_000):
            v = np.ascontiguousarray(vectors[i : i + 100_000], dtype=np.float32)
            cols = {
                "id": pa.array(ids[i : i + 100_000]),
                "vector": pa.FixedSizeListArray.from_arrays(pa.array(v.ravel()), d),
            }
            if metadata:
                cols["labels"] = pa.array(
                    [m["labels"] for m in metadata[i : i + 100_000]]
                )
            if self.table is None:
                self.table = db.create_table("bench", pa.table(cols))
            else:
                self.table.add(pa.table(cols))
        self.table.create_index(
            "vector",
            config=HnswSq(
                distance_type="dot",
                num_partitions=1,
                m=HNSW_M,
                ef_construction=HNSW_EF_CONSTRUCTION,
            )
        )
        self.ef = 64

    def set_search(self, params: dict) -> None:
        """Remember the HNSW ef used by subsequent queries."""
        self.ef = params["ef"]

    def search(self, q: np.ndarray, k: int, flt: dict | None = None) -> list[int]:
        """Vector search with dot distance; neutral filters become a prefiltered SQL where clause."""
        s = (
            self.table.search(q)
            .distance_type("dot")
            .ef(self.ef)
            .limit(k)
            .select(["id", "_distance"])
        )
        if flt:
            value = flt["value"] if flt["op"] == "gte" else f"'{flt['value']}'"
            s = s.where(f"{flt['field']} {_sql_op(flt)} {value}", prefilter=True)
        return s.to_arrow().column("id").to_pylist()

    def close(self) -> None:
        """Delete the temp table directory."""
        shutil.rmtree(self.dir, ignore_errors=True)


class QdrantLocalEngine:
    """qdrant-client local mode (in-process, in-memory); exact, since local mode does not use HNSW."""

    name, sweep = "qdrant-local", []

    def build(
        self, ids: np.ndarray, vectors: np.ndarray, metadata: list[dict] | None
    ) -> None:
        """Create a DOT collection and upsert points in batches; the payload holds id and labels."""
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, PointStruct, VectorParams

        self.client = QdrantClient(":memory:")
        self.client.create_collection(
            "bench",
            vectors_config=VectorParams(size=vectors.shape[1], distance=Distance.DOT),
        )
        for i in range(0, len(ids), BATCH):
            self.client.upsert(
                "bench",
                [
                    PointStruct(
                        id=int(ids[i + j]),
                        vector=v,
                        payload=metadata[i + j] if metadata else None,
                    )
                    for j, v in enumerate(vectors[i : i + BATCH].tolist())
                ],
            )

    def set_search(self, params: dict) -> None:
        """No search parameters in local mode."""

    def search(self, q: np.ndarray, k: int, flt: dict | None = None) -> list[int]:
        """query_points with an optional Range (gte) or MatchValue (eq) payload filter."""
        from qdrant_client.models import FieldCondition, Filter, MatchValue, Range

        f = None
        if flt:
            cond = (
                FieldCondition(key=flt["field"], range=Range(gte=flt["value"]))
                if flt["op"] == "gte"
                else FieldCondition(
                    key=flt["field"], match=MatchValue(value=flt["value"])
                )
            )
            f = Filter(must=[cond])
        return [
            p.id
            for p in self.client.query_points(
                "bench", query=q.tolist(), limit=k, query_filter=f
            ).points
        ]

    def close(self) -> None:
        """Close the local client."""
        self.client.close()


class FaissEngine:
    """FAISS in-process: 'flat' = IndexFlatIP (exact baseline), 'hnsw' = IndexHNSWFlat (efSearch sweep).

    Filters use an IDSelectorBatch over the row positions that satisfy the filter (built once per filter).
    """

    def __init__(self, kind: str) -> None:
        """kind is 'flat' or 'hnsw'."""
        self.kind, self.name = kind, f"faiss-{kind}"
        self.sweep = EF_SWEEP if kind == "hnsw" else []
        self.ef, self.selectors = 64, {}

    def build(
        self, ids: np.ndarray, vectors: np.ndarray, metadata: list[dict] | None
    ) -> None:
        """Add all vectors; FAISS ids are row positions and self.ids maps them back to doc ids."""
        import faiss

        d = vectors.shape[1]
        if self.kind == "flat":
            self.index = faiss.IndexFlatIP(d)
        else:
            self.index = faiss.IndexHNSWFlat(d, HNSW_M, faiss.METRIC_INNER_PRODUCT)
            self.index.hnsw.efConstruction = HNSW_EF_CONSTRUCTION
        for i in range(0, len(ids), 100_000):
            self.index.add(
                np.ascontiguousarray(vectors[i : i + 100_000], dtype=np.float32)
            )
        self.ids, self.meta = np.asarray(ids), metadata

    def set_search(self, params: dict) -> None:
        """Remember efSearch for HNSW queries."""
        self.ef = params["ef"]

    def _selector(self, flt: dict) -> object:
        """IDSelectorBatch of the row positions passing flt (cached per filter; the array is kept alive)."""
        import faiss

        key = (flt["field"], flt["op"], flt["value"])
        if key not in self.selectors:
            if flt["op"] == "gte":
                pos = np.nonzero(self.ids >= flt["value"])[0].astype(np.int64)
            else:
                pos = np.array(
                    [
                        i
                        for i, m in enumerate(self.meta)
                        if m[flt["field"]] == flt["value"]
                    ],
                    dtype=np.int64,
                )
            self.selectors[key] = (faiss.IDSelectorBatch(pos), pos)
        return self.selectors[key][0]

    def search(self, q: np.ndarray, k: int, flt: dict | None = None) -> list[int]:
        """Single-query search with an optional selector; -1 (fewer than k hits) is dropped."""
        import faiss

        sel = self._selector(flt) if flt else None
        params = (
            faiss.SearchParametersHNSW(efSearch=self.ef, sel=sel)
            if self.kind == "hnsw"
            else faiss.SearchParameters(sel=sel)
        )
        _, idx = self.index.search(
            np.asarray(q, dtype=np.float32)[None, :], k, params=params
        )
        return [int(self.ids[i]) for i in idx[0] if i >= 0]

    def close(self) -> None:
        """Drop the index."""
        self.index = None


class ZvecEngine:
    """zvec embedded collection (on disk, mmap) with an HNSW IP index; mirrors VectorDBBench's zvec adapter."""

    name, sweep = "zvec", EF_SWEEP

    def build(
        self, ids: np.ndarray, vectors: np.ndarray, metadata: list[dict] | None
    ) -> None:
        """Create the collection in a temp dir, insert in batches, then optimize (builds the index)."""
        import zvec

        zvec.init(log_level=zvec.LogLevel.WARN)
        fields = [
            zvec.FieldSchema(
                "id",
                zvec.DataType.INT64,
                nullable=False,
                index_param=zvec.InvertIndexParam(enable_range_optimization=True),
            )
        ]
        if metadata:
            fields.append(
                zvec.FieldSchema(
                    "labels",
                    zvec.DataType.STRING,
                    nullable=False,
                    index_param=zvec.InvertIndexParam(enable_range_optimization=False),
                )
            )
        schema = zvec.CollectionSchema(
            name="bench",
            fields=fields,
            vectors=[
                zvec.VectorSchema(
                    "dense",
                    zvec.DataType.VECTOR_FP32,
                    dimension=vectors.shape[1],
                    index_param=zvec.HnswIndexParam(
                        metric_type=zvec.MetricType.IP,
                        m=HNSW_M,
                        ef_construction=HNSW_EF_CONSTRUCTION,
                    ),
                )
            ],
        )
        self.dir = Path(tempfile.mkdtemp(prefix="bench-zvec-"))
        self.col = zvec.create_and_open(
            path=str(self.dir / "c"),
            schema=schema,
            option=zvec.CollectionOption(read_only=False, enable_mmap=True),
        )
        for i in range(0, len(ids), BATCH):
            self.col.insert(
                [
                    zvec.Doc(
                        id=str(ids[i + j]),
                        vectors={"dense": v},
                        fields={
                            "id": int(ids[i + j]),
                            **(
                                {"labels": metadata[i + j]["labels"]}
                                if metadata
                                else {}
                            ),
                        },
                    )
                    for j, v in enumerate(vectors[i : i + BATCH].tolist())
                ]
            )
        self.col.optimize(option=zvec.OptimizeOption())
        self.param = zvec.HnswQueryParam(ef=64)

    def set_search(self, params: dict) -> None:
        """Set HNSW ef for subsequent queries."""
        import zvec

        self.param = zvec.HnswQueryParam(ef=params["ef"])

    def search(self, q: np.ndarray, k: int, flt: dict | None = None) -> list[int]:
        """Vector query with an optional filter expression (`id >= v` / `labels = 'v'`)."""
        import zvec

        expr = ""
        if flt:
            value = flt["value"] if flt["op"] == "gte" else f"'{flt['value']}'"
            expr = f"{flt['field']} {_sql_op(flt)} {value}"
        res = self.col.query(
            output_fields=[],
            topk=k,
            filter=expr,
            vectors=zvec.VectorQuery(
                field_name="dense", vector=q.tolist(), param=self.param
            ),
        )
        return [int(r.id) for r in res]

    def close(self) -> None:
        """Destroy the collection and delete its directory."""
        self.col.destroy()
        shutil.rmtree(self.dir, ignore_errors=True)


class SqliteVecEngine:
    """sqlite-vec vec0 virtual table (exact brute-force KNN) with metadata columns for filtering.

    The database is a temp file so each thread can open its own connection (sqlite connections are per thread).
    """

    name, sweep = "sqlite-vec", []

    def _conn(self) -> sqlite3.Connection:
        """This thread's connection, with the sqlite-vec extension loaded."""
        import sqlite_vec

        c = getattr(self.local, "c", None)
        if c is None:
            c = self.local.c = sqlite3.connect(self.path)
            c.enable_load_extension(True)
            sqlite_vec.load(c)
        return c

    def build(
        self, ids: np.ndarray, vectors: np.ndarray, metadata: list[dict] | None
    ) -> None:
        """Create a cosine vec0 table with id/labels metadata columns and insert in batches."""
        self.dir = Path(tempfile.mkdtemp(prefix="bench-sqlitevec-"))
        self.path, self.local = str(self.dir / "db.sqlite"), threading.local()
        c = self._conn()
        c.execute(
            f"create virtual table v using vec0(embedding float[{vectors.shape[1]}] distance_metric=cosine, "
            "id integer, labels text)"
        )
        for i in range(0, len(ids), BATCH):
            c.executemany(
                "insert into v(embedding, id, labels) values (?, ?, ?)",
                [
                    (
                        np.asarray(vectors[n], dtype=np.float32).tobytes(),
                        int(ids[n]),
                        metadata[n]["labels"] if metadata else "",
                    )
                    for n in range(i, min(i + BATCH, len(ids)))
                ],
            )
        c.commit()

    def set_search(self, params: dict) -> None:
        """No search parameters (exact)."""

    def search(self, q: np.ndarray, k: int, flt: dict | None = None) -> list[int]:
        """KNN via `embedding match ? and k = ?`, plus a metadata constraint when filtered."""
        sql, args = (
            "select id from v where embedding match ? and k = ?",
            [np.asarray(q, dtype=np.float32).tobytes(), k],
        )
        if flt:
            sql += f" and {flt['field']} {_sql_op(flt)} ?"
            args.append(flt["value"])
        return [r[0] for r in self._conn().execute(sql + " order by distance", args)]

    def close(self) -> None:
        """Delete the database directory."""
        shutil.rmtree(self.dir, ignore_errors=True)


class DuckdbVssEngine:
    """DuckDB in-memory table with the VSS extension's HNSW index (metric 'ip'); one cursor per thread."""

    name, sweep = "duckdb-vss", EF_SWEEP

    def build(
        self, ids: np.ndarray, vectors: np.ndarray, metadata: list[dict] | None
    ) -> None:
        """Load rows through Arrow in batches, then CREATE INDEX ... USING HNSW."""
        import duckdb
        import pyarrow as pa

        self.d, self.local, self.ef = vectors.shape[1], threading.local(), 64
        self.con = duckdb.connect()
        self.con.execute("INSTALL vss; LOAD vss")
        self.con.execute(
            f"CREATE TABLE t (id BIGINT, labels VARCHAR, v FLOAT[{self.d}])"
        )
        for i in range(0, len(ids), 100_000):
            v = np.ascontiguousarray(vectors[i : i + 100_000], dtype=np.float32)
            labels = (
                [m["labels"] for m in metadata[i : i + 100_000]]
                if metadata
                else [""] * len(v)
            )
            batch = pa.table(
                {
                    "id": pa.array(ids[i : i + 100_000]),
                    "labels": pa.array(labels),
                    "v": pa.FixedSizeListArray.from_arrays(pa.array(v.ravel()), self.d),
                }
            )
            self.con.register("batch", batch)
            self.con.execute("INSERT INTO t SELECT * FROM batch")
            self.con.unregister("batch")
        self.con.execute(
            f"CREATE INDEX idx ON t USING HNSW (v) WITH (metric = 'ip', M = {HNSW_M}, "
            f"ef_construction = {HNSW_EF_CONSTRUCTION})"
        )

    def _cur(self) -> object:
        """This thread's cursor (DuckDB connections must not be shared across threads), with ef applied."""
        if getattr(self.local, "c", None) is None:
            self.local.c, self.local.ef = self.con.cursor(), None
        if self.local.ef != self.ef:
            self.local.c.execute(f"SET hnsw_ef_search = {self.ef}")
            self.local.ef = self.ef
        return self.local.c

    def set_search(self, params: dict) -> None:
        """Set hnsw_ef_search (applied lazily per cursor)."""
        self.ef = params["ef"]

    def search(self, q: np.ndarray, k: int, flt: dict | None = None) -> list[int]:
        """ORDER BY array_negative_inner_product LIMIT k; a WHERE clause is added when filtered.

        The query vector is inlined as a literal: binding a 768-float list as a prepared parameter costs about
        35 ms per call in duckdb 1.5.6 (even for SELECT 1), against 2.9 ms for the whole query with a literal.
        """
        where, args = "", []
        if flt:
            where, args = f"WHERE {flt['field']} {_sql_op(flt)} ?", [flt["value"]]
        vec = "[" + ",".join(map(str, np.asarray(q, dtype=np.float32).tolist())) + "]"
        sql = f"SELECT id FROM t {where} ORDER BY array_negative_inner_product(v, {vec}::FLOAT[{self.d}]) LIMIT {k}"
        return [r[0] for r in self._cur().execute(sql, args).fetchall()]

    def close(self) -> None:
        """Close the connection."""
        self.con.close()


class MossTextEngine:
    """Moss with its built-in moss-minilm model: builds from text and embeds each query inside search().

    The sweep is Moss's only query knob, alpha (1.0 = vector only, 0.8 = SDK default hybrid with keyword search).
    """

    name, sweep = "moss", [{"alpha": 1.0}, {"alpha": 0.8}]

    def __init__(self) -> None:
        """Create the engine; the session opens in build()."""
        self.session, self.alpha = None, 1.0

    async def build(self, ids: np.ndarray, texts: list[str], metadata: list[dict] | None = None) -> None:
        """Open a moss-minilm session and add text docs, 100 per call (built-in ingest memory grows per call)."""
        import os

        from dotenv import load_dotenv
        from moss import DocumentInfo, MossClient

        if "MOSS_ENV_FILE" in os.environ:
            load_dotenv(os.environ["MOSS_ENV_FILE"], override=True)
        client = MossClient(os.environ["MOSS_PROJECT_ID"], os.environ["MOSS_PROJECT_KEY"])
        self.session = await client.session(f"bench-{uuid.uuid4().hex[:8]}", model_id="moss-minilm")
        for i in range(0, len(ids), 100):
            await self.session.add_docs([DocumentInfo(id=str(ids[n]), text=texts[n]) for n in range(i, min(i + 100, len(ids)))])

    def set_search(self, params: dict) -> None:
        """Set alpha for subsequent queries."""
        self.alpha = params["alpha"]

    async def search(self, q: str, k: int, flt: dict | None = None) -> list[int]:
        """Text query; Moss embeds it with the built-in model."""
        from moss import QueryOptions

        r = await self.session.query(q, QueryOptions(top_k=k, alpha=self.alpha))
        return [int(d.id) for d in r.docs]

    async def close(self) -> None:
        """Send Moss's final telemetry and free the session."""
        await self.session.close()


class QueryEmbedder:
    """Text mode for a vector engine: indexes precomputed MiniLM corpus vectors, embeds each query with fastembed
    all-MiniLM-L6-v2 (the same weights as moss-minilm) inside search(), so latency is end to end."""

    def __init__(self, engine: object, cache_dir: str) -> None:
        """Wrap `engine` and load the fastembed model once."""
        from fastembed import TextEmbedding

        self.engine, self.name, self.sweep = engine, engine.name, engine.sweep
        from bench_data import MINILM, MINILM_MAX_TOKENS

        self.model = TextEmbedding(MINILM, cache_dir=cache_dir)
        self.model.model.tokenizer.enable_truncation(max_length=MINILM_MAX_TOKENS)  # match moss-minilm

    def build(self, ids: np.ndarray, vectors: np.ndarray, metadata: list[dict] | None = None) -> None:
        """Index the precomputed corpus vectors."""
        self.engine.build(ids, vectors, metadata)

    def set_search(self, params: dict) -> None:
        """Forward the sweep setting."""
        self.engine.set_search(params)

    def search(self, q: str, k: int, flt: dict | None = None) -> list[int]:
        """Embed the query (unit-normalized), then search the wrapped engine."""
        v = next(iter(self.model.embed([q])))
        return self.engine.search(v / np.linalg.norm(v), k, flt)

    def close(self) -> None:
        """Close the wrapped engine."""
        self.engine.close()


def faiss_flat() -> FaissEngine:
    """FAISS exact baseline (IndexFlatIP)."""
    return FaissEngine("flat")


def faiss_hnsw() -> FaissEngine:
    """FAISS HNSW (IndexHNSWFlat) with an efSearch sweep."""
    return FaissEngine("hnsw")


ENGINES = {
    "moss": MossEngine,
    "chroma": ChromaEngine,
    "lancedb": LanceEngine,
    "qdrant-local": QdrantLocalEngine,
    "faiss-flat": faiss_flat,
    "faiss-hnsw": faiss_hnsw,
    "zvec": ZvecEngine,
    "sqlite-vec": SqliteVecEngine,
    "duckdb-vss": DuckdbVssEngine,
}


def make_engine(name: str, text: bool, cache_dir: str) -> object:
    """Engine for a dataset kind: on text datasets Moss uses its built-in model, the others wrap QueryEmbedder."""
    if not text:
        return ENGINES[name]()
    return MossTextEngine() if name == "moss" else QueryEmbedder(ENGINES[name](), cache_dir)
