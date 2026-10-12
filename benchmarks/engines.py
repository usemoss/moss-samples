"""Engine adapters: every engine runs off the shelf, with its library's default index and search
settings.

Contract (used by run.py), identical for all engines:
  name: str              short identifier written into result files
  METRICS: dict          metric mode -> distance used: "default" = the library's default metric,
                         "ip" = inner product
                         (cosine where the engine has none); an engine whose default is already
                         inner product has only "default"
  metric: str            the distance this instance uses (METRICS[mode])
  sweep: list[dict]      search settings for the serial stage; {} = the library default, which
                         every sweep starts with ([{}] = exact engine, one point)
  build(ids, vectors, metadata) -> None     index all docs (ids int64, vectors (n, d) float32,
                                            metadata or None)
  set_search(params) -> None                apply one sweep setting; {} restores the library default
  search(q, k, flt) -> list[int]            top-k doc ids for one query vector; flt is a neutral
                                            filter or None
  close() -> None                           free resources

Moss's build/search/close are coroutines (its public API is async); the other engines are synchronous.
Vectors are L2-normalized, so l2, inner product and cosine rank documents identically.
Each search returns what the library returns by default (never vectors unless that is its default);
SQL engines
select id, labels and the distance where the index allows it.

A neutral filter is {"field": "id", "op": "gte", "value": int} or {"field": "labels", "op": "eq",
"value": str}. Metadata rows are {"id": int, "labels": str}.
"""

import shutil
import sqlite3
import tempfile
import uuid
from pathlib import Path

import numpy as np

EF_SWEEP = [{}] + [
    {"ef": e} for e in (16, 32, 64, 100, 128, 160, 200, 256, 320, 400, 512, 768, 1024)
]
BATCH = 1000
FAISS_HNSW_M = 32  # faiss's C++ default; the Python constructor requires M


def _sql_op(flt: dict) -> str:
    """SQL comparison operator for a neutral filter."""
    return ">=" if flt["op"] == "gte" else "="


class MossEngine:
    """Moss through its public Python API: one uniquely named SessionIndex with custom vectors,
    never pushed.
    """

    name, sweep, METRICS = "moss", [{}], {"default": "ip"}

    def __init__(self, mode: str = "default") -> None:
        """Create the engine; the session opens in build()."""
        self.session, self.metric = None, self.METRICS[mode]

    async def build(
        self, ids: np.ndarray, vectors: np.ndarray, metadata: list[dict] | None
    ) -> None:
        """Open a custom-embedding session and add docs in batches of BATCH (keeps Python lists small)."""
        import os

        from dotenv import load_dotenv
        from moss import DocumentInfo, MossClient

        if "MOSS_ENV_FILE" in os.environ:
            load_dotenv(os.environ["MOSS_ENV_FILE"], override=True)
        client = MossClient(os.environ["MOSS_PROJECT_ID"], os.environ["MOSS_PROJECT_KEY"])
        self.session = await client.session(f"bench-{uuid.uuid4().hex[:8]}", model_id="custom")
        for i in range(0, len(ids), BATCH):
            docs = [
                DocumentInfo(
                    id=str(ids[i + j]),
                    text="",
                    embedding=row,
                    metadata={k: str(v) for k, v in metadata[i + j].items()} if metadata else None,
                )
                for j, row in enumerate(vectors[i : i + BATCH].tolist())
            ]
            await self.session.add_docs(docs)

    def set_search(self, params: dict) -> None:
        """Moss has no search parameters (exact search)."""

    async def search(self, q: np.ndarray, k: int, flt: dict | None = None) -> list[int]:
        """Vector-only query (alpha=1.0, there is no query text); filters use Moss's string-valued, numeric-aware
        operators."""
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
    """Chroma in-process (PersistentClient in a temp dir) with its default HNSW index (l2 by default).

    A persistent client is required for the ef sweep: chromadb 1.5.9 stores a modified ef_search but the loaded
    index keeps the old value until the client is reopened (verified: recall unchanged on EphemeralClient).
    """

    name, sweep, METRICS = "chroma", EF_SWEEP, {"default": "l2", "ip": "ip"}

    def __init__(self, mode: str = "default") -> None:
        """mode picks the metric (see METRICS)."""
        self.metric = self.METRICS[mode]

    def build(self, ids: np.ndarray, vectors: np.ndarray, metadata: list[dict] | None) -> None:
        """Create a collection (only the space is set, in "ip" mode) and add docs in the client's max batch size."""
        import chromadb
        from chromadb.config import Settings

        self.dir = Path(tempfile.mkdtemp(prefix="bench-chroma-"))
        client = chromadb.PersistentClient(str(self.dir), Settings(anonymized_telemetry=False))
        self.col = client.create_collection(
            "bench",
            configuration={"hnsw": {"space": "ip"}} if self.metric == "ip" else None,
        )
        self.default_ef = self.col.configuration_json["hnsw"]["ef_search"]
        step = client.get_max_batch_size()
        for i in range(0, len(ids), step):
            self.col.add(
                ids=[str(x) for x in ids[i : i + step]],
                embeddings=vectors[i : i + step],
                metadatas=metadata[i : i + step] if metadata else None,
            )

    def set_search(self, params: dict) -> None:
        """Set HNSW ef_search (the default when params is {}), then reopen the client so the loaded index uses it."""
        import chromadb
        from chromadb.config import Settings

        settings = Settings(anonymized_telemetry=False)
        ef = params.get("ef", self.default_ef)
        self.col.modify(configuration={"hnsw": {"ef_search": ef}})
        chromadb.PersistentClient(str(self.dir), settings).clear_system_cache()
        self.col = chromadb.PersistentClient(str(self.dir), settings).get_collection("bench")

    def search(self, q: np.ndarray, k: int, flt: dict | None = None) -> list[int]:
        """Query by embedding (default include: metadatas, documents, distances); neutral filters map to Chroma's
        where clause ($gte / $eq)."""
        where = {flt["field"]: {f"${flt['op']}": flt["value"]}} if flt else None
        return [
            int(x) for x in self.col.query(query_embeddings=[q], n_results=k, where=where)["ids"][0]
        ]

    def close(self) -> None:
        """Delete the temp database directory."""
        shutil.rmtree(self.dir, ignore_errors=True)


class LanceEngine:
    """LanceDB embedded. 'ivfpq' = `create_index()` with no config (IVF_PQ, the library default; sweep:
    refine_factor, which re-ranks with full vectors), 'hnsw' = `IvfHnswSq()` defaults (the docs' "best
    recall/latency for unfiltered search"; sweep: ef). Filters are where clauses, prefiltered by default.
    """

    METRICS = {"default": "l2", "ip": "dot"}

    def __init__(self, kind: str, mode: str = "default") -> None:
        """kind is 'ivfpq' or 'hnsw'; mode picks the metric (see METRICS)."""
        self.kind, self.metric = kind, self.METRICS[mode]
        self.name = "lancedb" if kind == "ivfpq" else "lancedb-hnsw"
        self.sweep = (
            EF_SWEEP
            if kind == "hnsw"
            else [{}] + [{"refine_factor": r} for r in (2, 5, 10, 20, 50)]
        )
        self.params: dict = {}

    def build(self, ids: np.ndarray, vectors: np.ndarray, metadata: list[dict] | None) -> None:
        """Write a Lance table in a temp dir (batches of 100k rows), then build the index (only the metric set, in
        "ip" mode)."""
        import lancedb
        import pyarrow as pa
        from lancedb.index import IvfHnswSq, IvfPq

        self.dir = Path(tempfile.mkdtemp(prefix="bench-lancedb-"))
        db, d, self.table = lancedb.connect(self.dir), vectors.shape[1], None
        for i in range(0, len(ids), 100_000):
            v = np.ascontiguousarray(vectors[i : i + 100_000], dtype=np.float32)
            cols = {
                "id": pa.array(ids[i : i + 100_000]),
                "vector": pa.FixedSizeListArray.from_arrays(pa.array(v.ravel()), d),
            }
            if metadata:
                cols["labels"] = pa.array([m["labels"] for m in metadata[i : i + 100_000]])
            if self.table is None:
                self.table = db.create_table("bench", pa.table(cols))
            else:
                self.table.add(pa.table(cols))
        if self.kind == "hnsw":
            self.table.create_index("vector", config=IvfHnswSq(distance_type=self.metric))
        elif self.metric == "l2":
            self.table.create_index("vector")
        else:
            self.table.create_index("vector", config=IvfPq(distance_type=self.metric))

    def set_search(self, params: dict) -> None:
        """Remember the sweep setting ({} = Lance's defaults: ef 1.5 x k, no refine)."""
        self.params = params

    def search(self, q: np.ndarray, k: int, flt: dict | None = None) -> list[int]:
        """Vector search with the index's metric (default output: every column, vector included); neutral filters
        become a where clause."""
        s = self.table.search(q).distance_type(self.metric).limit(k)
        if "ef" in self.params:
            s = s.ef(self.params["ef"])
        if "refine_factor" in self.params:
            s = s.refine_factor(self.params["refine_factor"])
        if flt:
            value = flt["value"] if flt["op"] == "gte" else f"'{flt['value']}'"
            s = s.where(f"{flt['field']} {_sql_op(flt)} {value}")
        return s.to_arrow().column("id").to_pylist()

    def close(self) -> None:
        """Delete the temp table directory."""
        shutil.rmtree(self.dir, ignore_errors=True)


class QdrantLocalEngine:
    """qdrant-client local mode (in-process, in-memory); exact, since local mode does not use HNSW. Qdrant has no
    default distance (VectorParams requires one), so DOT is used in every mode."""

    name, sweep, METRICS = "qdrant-local", [{}], {"default": "dot"}

    def __init__(self, mode: str = "default") -> None:
        """mode picks the metric (see METRICS)."""
        self.metric = self.METRICS[mode]

    def build(self, ids: np.ndarray, vectors: np.ndarray, metadata: list[dict] | None) -> None:
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
        """query_points (default: payload, no vectors) with an optional Range (gte) or MatchValue (eq) filter."""
        from qdrant_client.models import FieldCondition, Filter, MatchValue, Range

        f = None
        if flt:
            cond = (
                FieldCondition(key=flt["field"], range=Range(gte=flt["value"]))
                if flt["op"] == "gte"
                else FieldCondition(key=flt["field"], match=MatchValue(value=flt["value"]))
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
    """FAISS in-process: 'flat' = IndexFlatL2 / IndexFlatIP (exact baseline), 'hnsw' = IndexHNSWFlat with M=32 and
    faiss's default efConstruction (40) and efSearch (16).

    Filters use an IDSelectorBatch over the row positions that satisfy the filter (built once per filter).
    """

    METRICS = {"default": "l2", "ip": "ip"}

    def __init__(self, kind: str, mode: str = "default") -> None:
        """kind is 'flat' or 'hnsw'; mode picks the metric (see METRICS)."""
        self.kind, self.name, self.metric = kind, f"faiss-{kind}", self.METRICS[mode]
        self.sweep = EF_SWEEP if kind == "hnsw" else [{}]
        self.selectors = {}

    def build(self, ids: np.ndarray, vectors: np.ndarray, metadata: list[dict] | None) -> None:
        """Add all vectors; FAISS ids are row positions and self.ids maps them back to doc ids."""
        import faiss

        d = vectors.shape[1]
        metric = faiss.METRIC_INNER_PRODUCT if self.metric == "ip" else faiss.METRIC_L2
        if self.kind == "flat":
            self.index = faiss.IndexFlat(d, metric)
        else:
            self.index = faiss.IndexHNSWFlat(d, FAISS_HNSW_M, metric)
            self.default_ef = self.index.hnsw.efSearch
        for i in range(0, len(ids), 100_000):
            self.index.add(np.ascontiguousarray(vectors[i : i + 100_000], dtype=np.float32))
        self.ids, self.meta = np.asarray(ids), metadata

    def set_search(self, params: dict) -> None:
        """Set efSearch for HNSW queries ({} = faiss's default)."""
        if self.kind == "hnsw":
            self.index.hnsw.efSearch = params.get("ef", self.default_ef)

    def _selector(self, flt: dict) -> object:
        """IDSelectorBatch of the row positions passing flt (cached per filter; the array is kept alive)."""
        import faiss

        key = (flt["field"], flt["op"], flt["value"])
        if key not in self.selectors:
            if flt["op"] == "gte":
                pos = np.nonzero(self.ids >= flt["value"])[0].astype(np.int64)
            else:
                pos = np.array(
                    [i for i, m in enumerate(self.meta) if m[flt["field"]] == flt["value"]],
                    dtype=np.int64,
                )
            self.selectors[key] = (faiss.IDSelectorBatch(pos), pos)
        return self.selectors[key][0]

    def search(self, q: np.ndarray, k: int, flt: dict | None = None) -> list[int]:
        """Single-query search (ids and distances); a filter passes a selector (HNSW: with the current efSearch);
        -1 (fewer than k hits) is dropped."""
        import faiss

        params = None
        if flt:
            sel = self._selector(flt)
            params = (
                faiss.SearchParametersHNSW(efSearch=self.index.hnsw.efSearch, sel=sel)
                if self.kind == "hnsw"
                else faiss.SearchParameters(sel=sel)
            )
        _, idx = self.index.search(np.asarray(q, dtype=np.float32)[None, :], k, params=params)
        return [int(self.ids[i]) for i in idx[0] if i >= 0]

    def close(self) -> None:
        """Drop the index."""
        self.index = None


class ZvecEngine:
    """zvec embedded collection (on disk) with its default HNSW index (inner product by default)."""

    name, sweep, METRICS = "zvec", EF_SWEEP, {"default": "ip"}

    def __init__(self, mode: str = "default") -> None:
        """mode picks the metric (see METRICS)."""
        self.metric = self.METRICS[mode]

    def build(self, ids: np.ndarray, vectors: np.ndarray, metadata: list[dict] | None) -> None:
        """Create the collection in a temp dir (default options), insert in batches, then optimize (builds the
        index). id and labels get default inverted indexes so they can be filtered."""
        import zvec

        zvec.init(log_level=zvec.LogLevel.WARN)
        fields = [
            zvec.FieldSchema(
                "id",
                zvec.DataType.INT64,
                nullable=False,
                index_param=zvec.InvertIndexParam(),
            )
        ]
        if metadata:
            fields.append(
                zvec.FieldSchema(
                    "labels",
                    zvec.DataType.STRING,
                    nullable=False,
                    index_param=zvec.InvertIndexParam(),
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
                    index_param=zvec.HnswIndexParam(),
                )
            ],
        )
        self.dir = Path(tempfile.mkdtemp(prefix="bench-zvec-"))
        self.col = zvec.create_and_open(path=str(self.dir / "c"), schema=schema)
        for i in range(0, len(ids), BATCH):
            self.col.insert(
                [
                    zvec.Doc(
                        id=str(ids[i + j]),
                        vectors={"dense": v},
                        fields={
                            "id": int(ids[i + j]),
                            **({"labels": metadata[i + j]["labels"]} if metadata else {}),
                        },
                    )
                    for j, v in enumerate(vectors[i : i + BATCH].tolist())
                ]
            )
        self.col.optimize(option=zvec.OptimizeOption())
        self.param = None

    def set_search(self, params: dict) -> None:
        """Set HNSW ef for subsequent queries (None = the index default)."""
        import zvec

        self.param = zvec.HnswQueryParam(ef=params["ef"]) if params else None

    def search(self, q: np.ndarray, k: int, flt: dict | None = None) -> list[int]:
        """Vector query (default output: all scalar fields) with an optional filter expression (`id >= v` /
        `labels = 'v'`)."""
        import zvec

        expr = None
        if flt:
            value = flt["value"] if flt["op"] == "gte" else f"'{flt['value']}'"
            expr = f"{flt['field']} {_sql_op(flt)} {value}"
        res = self.col.query(
            queries=zvec.Query(field_name="dense", vector=q.tolist(), param=self.param),
            topk=k,
            filter=expr,
        )
        return [int(r.id) for r in res]

    def close(self) -> None:
        """Destroy the collection and delete its directory."""
        self.col.destroy()
        shutil.rmtree(self.dir, ignore_errors=True)


class SqliteVecEngine:
    """sqlite-vec vec0 virtual table in a temp file (exact brute-force KNN, l2 by default, cosine in "ip" mode since
    vec0 has no inner product) with metadata columns for filtering."""

    name, sweep, METRICS = "sqlite-vec", [{}], {"default": "l2", "ip": "cosine"}

    def __init__(self, mode: str = "default") -> None:
        """mode picks the metric (see METRICS)."""
        self.metric = self.METRICS[mode]

    def build(self, ids: np.ndarray, vectors: np.ndarray, metadata: list[dict] | None) -> None:
        """Create a vec0 table with id/labels metadata columns and insert in batches."""
        import sqlite_vec

        self.dir = Path(tempfile.mkdtemp(prefix="bench-sqlitevec-"))
        self.con = sqlite3.connect(self.dir / "db.sqlite")
        self.con.enable_load_extension(True)
        sqlite_vec.load(self.con)
        metric = " distance_metric=cosine" if self.metric == "cosine" else ""
        self.con.execute(
            f"create virtual table v using vec0(embedding float[{vectors.shape[1]}]{metric}, id integer, labels text)"
        )
        for i in range(0, len(ids), BATCH):
            self.con.executemany(
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
        self.con.commit()

    def set_search(self, params: dict) -> None:
        """No search parameters (exact)."""

    def search(self, q: np.ndarray, k: int, flt: dict | None = None) -> list[int]:
        """KNN via `embedding match ? and k = ?`, plus a metadata constraint when filtered."""
        sql, args = (
            "select id, labels, distance from v where embedding match ? and k = ?",
            [np.asarray(q, dtype=np.float32).tobytes(), k],
        )
        if flt:
            sql += f" and {flt['field']} {_sql_op(flt)} ?"
            args.append(flt["value"])
        return [r[0] for r in self.con.execute(sql + " order by distance", args)]

    def close(self) -> None:
        """Close the connection and delete the database directory."""
        self.con.close()
        shutil.rmtree(self.dir, ignore_errors=True)


class DuckdbVssEngine:
    """DuckDB in-memory table with the VSS extension's default HNSW index (l2sq by default, 'ip' in "ip" mode)."""

    name, sweep, METRICS = "duckdb-vss", EF_SWEEP, {"default": "l2sq", "ip": "ip"}

    def __init__(self, mode: str = "default") -> None:
        """mode picks the metric (see METRICS)."""
        self.metric = self.METRICS[mode]

    def build(self, ids: np.ndarray, vectors: np.ndarray, metadata: list[dict] | None) -> None:
        """Load rows through Arrow in batches, then CREATE INDEX ... USING HNSW (only the metric set, in "ip" mode)."""
        import duckdb
        import pyarrow as pa

        self.d = vectors.shape[1]
        self.con = duckdb.connect()
        self.con.execute("INSTALL vss; LOAD vss")
        self.con.execute(f"CREATE TABLE t (id BIGINT, labels VARCHAR, v FLOAT[{self.d}])")
        for i in range(0, len(ids), 100_000):
            v = np.ascontiguousarray(vectors[i : i + 100_000], dtype=np.float32)
            labels = [m["labels"] for m in metadata[i : i + 100_000]] if metadata else [""] * len(v)
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
        with_ = " WITH (metric = 'ip')" if self.metric == "ip" else ""
        self.con.execute(f"CREATE INDEX idx ON t USING HNSW (v){with_}")
        # the ORDER BY function must match the index metric, or the index is not used
        self.dist = "array_negative_inner_product" if self.metric == "ip" else "array_distance"

    def set_search(self, params: dict) -> None:
        """Set hnsw_ef_search, or reset it to the index default for {}."""
        if params:
            self.con.execute(f"SET hnsw_ef_search = {params['ef']}")
        else:
            self.con.execute("RESET hnsw_ef_search")

    def search(self, q: np.ndarray, k: int, flt: dict | None = None) -> list[int]:
        """ORDER BY <metric distance> LIMIT k; a WHERE clause is added when filtered.

        The query vector is inlined as a literal: binding a 768-float list as a prepared parameter costs about
        35 ms per call in duckdb 1.5.6 (even for SELECT 1), against 2.9 ms for the whole query with a literal.
        """
        where, args = "", []
        if flt:
            where, args = f"WHERE {flt['field']} {_sql_op(flt)} ?", [flt["value"]]
        vec = "[" + ",".join(map(str, np.asarray(q, dtype=np.float32).tolist())) + "]"
        sql = f"SELECT id, labels FROM t {where} ORDER BY {self.dist}(v, {vec}::FLOAT[{self.d}]) LIMIT {k}"
        return [r[0] for r in self.con.execute(sql, args).fetchall()]

    def close(self) -> None:
        """Close the connection."""
        self.con.close()


class MossTextEngine:
    """Moss with its built-in moss-minilm model: builds from text and embeds each query inside search().

    The sweep is Moss's only query knob, alpha: {} = the SDK default (0.8, hybrid with keyword search), then 1.0
    (vector only).
    """

    name, sweep, METRICS = "moss", [{}, {"alpha": 1.0}], {"default": "ip"}

    def __init__(self, mode: str = "default") -> None:
        """Create the engine; the session opens in build()."""
        self.session, self.alpha, self.metric = None, None, self.METRICS[mode]

    async def build(
        self, ids: np.ndarray, texts: list[str], metadata: list[dict] | None = None
    ) -> None:
        """Open a moss-minilm session and add text docs, 100 per call (built-in ingest memory grows per call)."""
        import os

        from dotenv import load_dotenv
        from moss import DocumentInfo, MossClient

        if "MOSS_ENV_FILE" in os.environ:
            load_dotenv(os.environ["MOSS_ENV_FILE"], override=True)
        client = MossClient(os.environ["MOSS_PROJECT_ID"], os.environ["MOSS_PROJECT_KEY"])
        self.session = await client.session(f"bench-{uuid.uuid4().hex[:8]}", model_id="moss-minilm")
        for i in range(0, len(ids), 100):
            await self.session.add_docs(
                [
                    DocumentInfo(id=str(ids[n]), text=texts[n])
                    for n in range(i, min(i + 100, len(ids)))
                ]
            )

    def set_search(self, params: dict) -> None:
        """Set alpha for subsequent queries (None = the SDK default)."""
        self.alpha = params.get("alpha")

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

        from bench_data import MINILM, MINILM_MAX_TOKENS

        self.engine, self.name, self.sweep = engine, engine.name, engine.sweep
        self.METRICS, self.metric = engine.METRICS, engine.metric
        self.model = TextEmbedding(MINILM, cache_dir=cache_dir)
        self.model.model.tokenizer.enable_truncation(
            max_length=MINILM_MAX_TOKENS
        )  # match moss-minilm

    def build(
        self, ids: np.ndarray, vectors: np.ndarray, metadata: list[dict] | None = None
    ) -> None:
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


def lancedb_ivfpq(mode: str = "default") -> LanceEngine:
    """LanceDB with its default index (IVF_PQ)."""
    return LanceEngine("ivfpq", mode)


def lancedb_hnsw(mode: str = "default") -> LanceEngine:
    """LanceDB with IVF_HNSW_SQ defaults."""
    return LanceEngine("hnsw", mode)


def faiss_flat(mode: str = "default") -> FaissEngine:
    """FAISS exact baseline (IndexFlatL2 / IndexFlatIP)."""
    return FaissEngine("flat", mode)


def faiss_hnsw(mode: str = "default") -> FaissEngine:
    """FAISS HNSW (IndexHNSWFlat) with an efSearch sweep."""
    return FaissEngine("hnsw", mode)


ENGINES = {
    "moss": MossEngine,
    "chroma": ChromaEngine,
    "lancedb": lancedb_ivfpq,
    "lancedb-hnsw": lancedb_hnsw,
    "qdrant-local": QdrantLocalEngine,
    "faiss-flat": faiss_flat,
    "faiss-hnsw": faiss_hnsw,
    "zvec": ZvecEngine,
    "sqlite-vec": SqliteVecEngine,
    "duckdb-vss": DuckdbVssEngine,
}


def make_engine(name: str, text: bool, cache_dir: str, mode: str) -> object:
    """Engine for a dataset kind and metric mode: on text datasets Moss uses its built-in model, the others wrap
    QueryEmbedder. Raises KeyError when the engine has no such mode."""
    if text and name == "moss":
        return MossTextEngine(mode)
    eng = ENGINES[name](mode)
    return QueryEmbedder(eng, cache_dir) if text else eng
