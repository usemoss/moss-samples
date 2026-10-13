"""Engine adapters for the benchmark, each running its library off the shelf.

Every engine uses its library's default index and search settings.

Contract (used by harness.py and the suite_*.py runners), identical for all engines (shared
parts in the Engine base class):
  name: str              short identifier written into result files
  METRICS: dict          metric mode -> distance used: "default" = the library's default metric,
                         "ip" = inner product (cosine where the engine has none); an engine whose
                         default is already inner product has only "default"
  MODULES: tuple         libraries imported in __init__, outside the build timer
  metric: str            the distance this instance uses (METRICS[mode])
  sweep: list[dict]      the primary search knob's settings (suite_tuning.py); {} = the library
                         default, which every sweep starts with ([{}] = exact engine, one point)
  extra: list[dict]      secondary-knob settings, measured by suite_tuning.py and reported apart
                         from the primary sweep ([] for most engines)
  open() -> None                            untimed setup before build (Moss: its session)
  build(ids, vectors, metadata) -> None     index all docs (ids int64, vectors (n, d) float32,
                                            metadata or None); timed as build_s
  set_search(params) -> None                apply one sweep setting; {} restores the library
                                            default
  search(q, k, flt) -> list[int]            top-k doc ids for one query vector; flt is a neutral
                                            filter or None
  close() -> None                           free resources

Moss's open/build/search/close are coroutines (its public API is async); the other engines are
synchronous. Vectors are L2-normalized, so l2, inner product and cosine rank documents
identically. Each search returns what the library returns by default (never vectors unless that is
its default); SQL engines select id, labels and the distance where the index allows it.

A neutral filter is {"field": "id", "op": "gte", "value": int} or {"field": "labels", "op": "eq",
"value": str}. Metadata rows are {"id": int, "labels": str}.
"""

import functools
import importlib
import os
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
    """Map a neutral filter's op to its SQL comparison operator.

    Args:
        flt: Neutral filter.

    Returns:
        ">=" for op "gte", "=" otherwise.
    """
    return ">=" if flt["op"] == "gte" else "="


class Engine:
    """Shared adapter behavior.

    Imports the adapter's libraries in __init__ (outside the build timer and before the memory
    baseline), offers an untimed open() hook, a no-op set_search for engines without search
    parameters, and a close() that deletes the adapter's temp dir.
    """

    sweep: list[dict] = [{}]
    extra: list[dict] = []
    MODULES: tuple[str, ...] = ()

    def __init__(self, mode: str = "default") -> None:
        """Import MODULES and set the metric for a mode.

        Args:
            mode: Metric mode, a key of METRICS.

        Raises:
            KeyError: mode is not a key of METRICS.
        """
        self.metric, self.dir = self.METRICS[mode], None
        for m in self.MODULES:
            importlib.import_module(m)

    def open(self) -> None:
        """Untimed setup before build(); none by default."""

    def set_search(self, params: dict) -> None:
        """No search parameters (exact search)."""

    def close(self) -> None:
        """Delete the adapter's temp dir, if it made one."""
        if self.dir:
            shutil.rmtree(self.dir, ignore_errors=True)


async def moss_session(model_id: str) -> object:
    """Open a uniquely named, never-pushed Moss session.

    Credentials come from MOSS_PROJECT_ID / MOSS_PROJECT_KEY, first loaded from the file named by
    MOSS_ENV_FILE when that is set. session() authenticates, looks up a same-named cloud index and,
    for a built-in model, loads the model (moss 1.15.1), so the adapters call this from open(),
    outside the build timer.

    Args:
        model_id: "custom" or a built-in model such as "moss-minilm".

    Returns:
        The SessionIndex.

    Raises:
        KeyError: MOSS_PROJECT_ID or MOSS_PROJECT_KEY is not set.
    """
    from dotenv import load_dotenv
    from moss import MossClient

    if "MOSS_ENV_FILE" in os.environ:
        load_dotenv(os.environ["MOSS_ENV_FILE"], override=True)
    client = MossClient(os.environ["MOSS_PROJECT_ID"], os.environ["MOSS_PROJECT_KEY"])
    return await client.session(f"bench-{uuid.uuid4().hex[:8]}", model_id=model_id)


class MossEngine(Engine):
    """Moss through its public Python API, with custom vectors.

    One uniquely named SessionIndex per run, never pushed.
    """

    name, METRICS, MODULES = "moss", {"default": "ip"}, ("dotenv", "moss")

    async def open(self) -> None:
        """Open the custom-embedding session (untimed; see moss_session)."""
        self.session = await moss_session("custom")

    async def build(
        self, ids: np.ndarray, vectors: np.ndarray, metadata: list[dict] | None
    ) -> None:
        """Add every doc to the session opened by open().

        Docs are added BATCH per call (keeps the Python lists small), with metadata values as
        strings.

        Args:
            ids: Doc ids, int64.
            vectors: Unit doc vectors, shape (n, d), float32.
            metadata: Metadata row per doc ({"id": int, "labels": str}), or None.
        """
        from moss import DocumentInfo

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

    async def search(self, q: np.ndarray, k: int, flt: dict | None = None) -> list[int]:
        """Run a vector-only query (alpha=1.0; there is no query text).

        Args:
            q: Unit query vector.
            k: Number of results.
            flt: Neutral filter, mapped to Moss's string-valued, numeric-aware $gte / $eq, or None.

        Returns:
            Top-k doc ids, best first.
        """
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


class ChromaEngine(Engine):
    """Chroma in-process (PersistentClient in a temp dir) with its default HNSW index.

    The space is l2 by default. A persistent client is required for the ef sweep: chromadb 1.5.9
    stores a modified ef_search but the loaded index keeps the old value until the client is
    reopened (verified: recall unchanged on EphemeralClient).
    """

    name, sweep, METRICS = "chroma", EF_SWEEP, {"default": "l2", "ip": "ip"}
    MODULES = ("chromadb", "chromadb.config")

    def build(self, ids: np.ndarray, vectors: np.ndarray, metadata: list[dict] | None) -> None:
        """Create a collection in a new temp dir and add every doc, in the client's max batch size.

        Only the space is configured, and only in "ip" mode. The default ef_search is kept for
        set_search({}).

        Args:
            ids: Doc ids, int64.
            vectors: Unit doc vectors, shape (n, d), float32.
            metadata: Metadata row per doc ({"id": int, "labels": str}), or None.
        """
        import chromadb
        from chromadb.config import Settings

        self.dir = Path(tempfile.mkdtemp(prefix="bench-chroma-"))
        self.client = chromadb.PersistentClient(str(self.dir), Settings(anonymized_telemetry=False))
        self.col = self.client.create_collection(
            "bench",
            configuration={"hnsw": {"space": "ip"}} if self.metric == "ip" else None,
        )
        self.default_ef = self.col.configuration_json["hnsw"]["ef_search"]
        step = self.client.get_max_batch_size()
        for i in range(0, len(ids), step):
            self.col.add(
                ids=[str(x) for x in ids[i : i + step]],
                embeddings=vectors[i : i + step],
                metadatas=metadata[i : i + step] if metadata else None,
            )

    def set_search(self, params: dict) -> None:
        """Set HNSW ef_search, then close and reopen the client so the loaded index uses it.

        modify() alone does not change the loaded index. close() stops the client's system and
        frees its loaded index; without it every reopen kept another copy of the index in memory
        (about 340 MB per reopen at cohere-100k).

        Args:
            params: Sweep setting, {"ef": int}; {} restores the default ef_search kept by build().
        """
        import chromadb
        from chromadb.config import Settings

        ef = params.get("ef", self.default_ef)
        self.col.modify(configuration={"hnsw": {"ef_search": ef}})
        self.client.close()
        self.client = chromadb.PersistentClient(str(self.dir), Settings(anonymized_telemetry=False))
        self.col = self.client.get_collection("bench")

    def search(self, q: np.ndarray, k: int, flt: dict | None = None) -> list[int]:
        """Query by embedding with Chroma's default include (metadatas, documents, distances).

        Args:
            q: Unit query vector.
            k: Number of results.
            flt: Neutral filter, mapped to a where clause ($gte / $eq), or None.

        Returns:
            Top-k doc ids, best first.
        """
        where = {flt["field"]: {f"${flt['op']}": flt["value"]}} if flt else None
        return [
            int(x) for x in self.col.query(query_embeddings=[q], n_results=k, where=where)["ids"][0]
        ]


class LanceEngine(Engine):
    """LanceDB embedded, with its default IVF_PQ index or IVF_HNSW_SQ.

    'ivfpq' = `create_index()` with no config (IVF_PQ, the library default; sweep: refine_factor,
    which re-ranks with full vectors), 'hnsw' = `IvfHnswSq()` defaults (the docs' "best
    recall/latency for unfiltered search"; sweep: ef; extra: refine_factor 2 / 5 / 10 at the default
    ef, since its scalar-quantized search alone levels off near 0.96 recall). Filters are where
    clauses, prefiltered by default.
    """

    METRICS = {"default": "l2", "ip": "dot"}
    MODULES = ("lancedb", "pyarrow", "lancedb.index")

    def __init__(self, kind: str, mode: str = "default") -> None:
        """Set the index kind, metric, name and sweep.

        Args:
            kind: "ivfpq" (the default IVF_PQ index, named lancedb) or "hnsw" (IVF_HNSW_SQ, named
                lancedb-hnsw).
            mode: Metric mode, a key of METRICS.

        Raises:
            KeyError: mode is not a key of METRICS.
        """
        super().__init__(mode)
        self.kind = kind
        self.name = "lancedb" if kind == "ivfpq" else "lancedb-hnsw"
        self.sweep = (
            EF_SWEEP if kind == "hnsw" else [{}] + [{"refine_factor": r} for r in (2, 5, 10, 20, 50)]
        )
        if kind == "hnsw":  # refine_factor re-ranks k x refine_factor candidates with full vectors
            self.extra = [{"refine_factor": r} for r in (2, 5, 10)]
        self.params: dict = {}

    def build(self, ids: np.ndarray, vectors: np.ndarray, metadata: list[dict] | None) -> None:
        """Write a Lance table in a new temp dir, then build its vector index.

        Rows (id, vector and, with metadata, labels) are written 100k at a time. The index config
        sets only the metric: IVF_HNSW_SQ always, IVF_PQ only in "ip" mode (in "default" mode
        create_index() gets no config).

        Args:
            ids: Doc ids, int64.
            vectors: Unit doc vectors, shape (n, d), float32.
            metadata: Metadata row per doc ({"id": int, "labels": str}), or None.
        """
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
        """Vector search with the index's metric and the current sweep setting.

        The default output has every column, vector included.

        Args:
            q: Unit query vector.
            k: Number of results.
            flt: Neutral filter, applied as a where clause, or None.

        Returns:
            Top-k doc ids, best first.
        """
        s = self.table.search(q).distance_type(self.metric).limit(k)
        if "ef" in self.params:
            s = s.ef(self.params["ef"])
        if "refine_factor" in self.params:
            s = s.refine_factor(self.params["refine_factor"])
        if flt:
            value = flt["value"] if flt["op"] == "gte" else f"'{flt['value']}'"
            s = s.where(f"{flt['field']} {_sql_op(flt)} {value}")
        return s.to_arrow().column("id").to_pylist()


class QdrantLocalEngine(Engine):
    """qdrant-client local mode (in-process, in-memory); exact, since local mode does not use HNSW.

    Qdrant has no default distance (VectorParams requires one), so DOT is used in every mode.
    """

    name, METRICS = "qdrant-local", {"default": "dot"}
    MODULES = ("qdrant_client", "qdrant_client.models")

    def build(self, ids: np.ndarray, vectors: np.ndarray, metadata: list[dict] | None) -> None:
        """Create an in-memory DOT collection and upsert every doc, BATCH points per call.

        Point ids are the doc ids; the payload is the metadata row (id and labels).

        Args:
            ids: Doc ids, int64.
            vectors: Unit doc vectors, shape (n, d), float32.
            metadata: Metadata row per doc ({"id": int, "labels": str}), or None.
        """
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

    def search(self, q: np.ndarray, k: int, flt: dict | None = None) -> list[int]:
        """Run query_points (default output: payload, no vectors).

        Args:
            q: Unit query vector.
            k: Number of results.
            flt: Neutral filter, mapped to a Range (gte) or MatchValue (eq) condition, or None.

        Returns:
            Top-k doc ids, best first.
        """
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


class FaissEngine(Engine):
    """FAISS in-process: 'flat' = IndexFlatL2 / IndexFlatIP (exact), 'hnsw' = IndexHNSWFlat.

    The flat index is the exact baseline. HNSW uses M=32 and faiss's default efConstruction (40) and
    efSearch (16). Filters use an IDSelectorBatch over the row positions that satisfy the filter
    (built once per filter).
    """

    METRICS, MODULES = {"default": "l2", "ip": "ip"}, ("faiss",)

    def __init__(self, kind: str, mode: str = "default") -> None:
        """Set the index kind, metric, name and sweep.

        Args:
            kind: "flat" (exact, named faiss-flat) or "hnsw" (named faiss-hnsw, with an ef sweep).
            mode: Metric mode, a key of METRICS.

        Raises:
            KeyError: mode is not a key of METRICS.
        """
        super().__init__(mode)
        self.kind, self.name = kind, f"faiss-{kind}"
        self.sweep = EF_SWEEP if kind == "hnsw" else [{}]

    def build(self, ids: np.ndarray, vectors: np.ndarray, metadata: list[dict] | None) -> None:
        """Create the index and add every vector, 100k rows at a time.

        FAISS ids are row positions: self.ids maps them back to doc ids and self.labels holds the
        label of each row (a numpy array, the way a FAISS application keeps filterable metadata).
        HNSW keeps faiss's default efSearch for set_search({}).

        Args:
            ids: Doc ids, int64.
            vectors: Unit doc vectors, shape (n, d), float32.
            metadata: Metadata row per doc ({"id": int, "labels": str}), or None.
        """
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
        self.ids = np.asarray(ids)
        self.labels = np.array([m["labels"] for m in metadata]) if metadata else None

    def set_search(self, params: dict) -> None:
        """Set efSearch for HNSW queries ({} = faiss's default)."""
        if self.kind == "hnsw":
            self.index.hnsw.efSearch = params.get("ef", self.default_ef)

    def _selector(self, flt: dict) -> tuple[object, np.ndarray]:
        """Build the IDSelectorBitmap of the rows that pass a filter, for one query.

        FAISS has no metadata filtering, so the application evaluates the predicate itself; it is
        evaluated per query, inside the timed search, so FAISS pays for its filter as the databases
        do.

        Args:
            flt: Neutral filter; "gte" compares doc ids, "eq" compares the labels.

        Returns:
            The selector and its bitmap, which must stay alive while the selector is in use.
        """
        import faiss

        mask = self.ids >= flt["value"] if flt["op"] == "gte" else self.labels == flt["value"]
        bits = np.packbits(mask, bitorder="little")  # faiss reads bit i of byte i >> 3
        return faiss.IDSelectorBitmap(len(mask), faiss.swig_ptr(bits)), bits

    def search(self, q: np.ndarray, k: int, flt: dict | None = None) -> list[int]:
        """Search one query (FAISS returns ids and distances).

        A filter is passed as a selector (HNSW: with the current efSearch). Positions of -1 (fewer
        than k hits) are dropped.

        Args:
            q: Unit query vector.
            k: Number of results.
            flt: Neutral filter, or None.

        Returns:
            Top-k doc ids, best first.
        """
        import faiss

        params = None
        if flt:
            sel, _bits = self._selector(flt)
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


class ZvecEngine(Engine):
    """zvec embedded collection (on disk) with its default HNSW index (inner product by default)."""

    name, sweep, METRICS, MODULES = "zvec", EF_SWEEP, {"default": "ip"}, ("zvec",)

    def build(self, ids: np.ndarray, vectors: np.ndarray, metadata: list[dict] | None) -> None:
        """Create a temp-dir zvec collection, insert every doc, then optimize (builds the index).

        The collection uses default options and a default HnswIndexParam; the id and labels fields
        get default inverted indexes so they can be filtered. Docs are inserted BATCH per call.

        Args:
            ids: Doc ids, int64.
            vectors: Unit doc vectors, shape (n, d), float32.
            metadata: Metadata row per doc ({"id": int, "labels": str}), or None.
        """
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
        """Run a vector query (default output: all scalar fields).

        Args:
            q: Unit query vector.
            k: Number of results.
            flt: Neutral filter, as a filter expression (`id >= v` or `labels = 'v'`), or None.

        Returns:
            Top-k doc ids, best first.
        """
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
        super().close()


class SqliteVecEngine(Engine):
    """sqlite-vec vec0 virtual table in a temp file, with metadata columns for filtering.

    Exact brute-force KNN: l2 by default, cosine in "ip" mode since vec0 has no inner product.
    """

    name, METRICS, MODULES = "sqlite-vec", {"default": "l2", "ip": "cosine"}, ("sqlite_vec",)

    def build(self, ids: np.ndarray, vectors: np.ndarray, metadata: list[dict] | None) -> None:
        """Create a vec0 table (embedding plus id and labels metadata columns) and insert every doc.

        Rows are inserted BATCH per executemany call and committed once; without metadata, labels is
        "".

        Args:
            ids: Doc ids, int64.
            vectors: Unit doc vectors, shape (n, d), float32.
            metadata: Metadata row per doc ({"id": int, "labels": str}), or None.
        """
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

    def search(self, q: np.ndarray, k: int, flt: dict | None = None) -> list[int]:
        """Run a KNN query (`embedding match ? and k = ?`) ordered by distance.

        Selects id, labels and distance.

        Args:
            q: Unit query vector.
            k: Number of results.
            flt: Neutral filter, added as a constraint on its metadata column, or None.

        Returns:
            Top-k doc ids, best first.
        """
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
        super().close()


class DuckdbVssEngine(Engine):
    """DuckDB in-memory table with the VSS extension's default HNSW index.

    The metric is l2sq by default and 'ip' in "ip" mode.
    """

    name, sweep, METRICS = "duckdb-vss", EF_SWEEP, {"default": "l2sq", "ip": "ip"}
    MODULES = ("duckdb", "pyarrow")

    def build(self, ids: np.ndarray, vectors: np.ndarray, metadata: list[dict] | None) -> None:
        """Load every doc into an in-memory table through Arrow, then create the HNSW index.

        Rows go in 100k at a time. CREATE INDEX ... USING HNSW sets only the metric, and only in
        "ip" mode. The ORDER BY distance function is chosen to match the index metric, since DuckDB
        uses the index only then.

        Args:
            ids: Doc ids, int64.
            vectors: Unit doc vectors, shape (n, d), float32.
            metadata: Metadata row per doc ({"id": int, "labels": str}), or None.
        """
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
        """Run ORDER BY <metric distance> LIMIT k, with a WHERE clause when filtered.

        The query vector is inlined as a literal: binding a 768-float list as a prepared parameter
        costs about 35 ms per call in duckdb 1.5.6 (even for SELECT 1), against 2.9 ms for the whole
        query with a literal.

        Args:
            q: Unit query vector.
            k: Number of results.
            flt: Neutral filter, or None.

        Returns:
            Top-k doc ids, best first.
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


class MossTextEngine(Engine):
    """Moss with its built-in moss-minilm model, indexing text and embedding queries in search().

    The sweep is Moss's only query knob, alpha: {} = the SDK default (0.8, hybrid with keyword
    search), then 1.0 (vector only).
    """

    name, sweep, METRICS = "moss", [{}, {"alpha": 1.0}], {"default": "ip"}
    MODULES, alpha = ("dotenv", "moss"), None

    async def open(self) -> None:
        """Open the moss-minilm session; session() also loads the model (untimed)."""
        self.session = await moss_session("moss-minilm")

    async def build(
        self, ids: np.ndarray, texts: list[str], metadata: list[dict] | None = None
    ) -> None:
        """Add every text doc to the session opened by open(), 100 per call.

        Small calls because built-in ingest memory grows per call.

        Args:
            ids: Doc ids (corpus positions).
            texts: Doc texts, in ids order.
            metadata: Unused; accepted for the shared build() signature.
        """
        from moss import DocumentInfo

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
        """Run a text query; Moss embeds it with the built-in model.

        Args:
            q: Query text.
            k: Number of results.
            flt: Ignored (text datasets have no filters).

        Returns:
            Top-k doc ids, best first.
        """
        from moss import QueryOptions

        r = await self.session.query(q, QueryOptions(top_k=k, alpha=self.alpha))
        return [int(d.id) for d in r.docs]

    async def close(self) -> None:
        """Send Moss's final telemetry and free the session."""
        await self.session.close()


class QueryEmbedder:
    """Text mode for a vector engine: queries are embedded inside search().

    It indexes precomputed MiniLM corpus vectors and embeds each query with fastembed
    all-MiniLM-L6-v2 (the same weights as moss-minilm), so latency is end to end.
    """

    def __init__(self, engine: object, cache_dir: str) -> None:
        """Wrap a vector engine and load the fastembed model once.

        The wrapper copies the engine's name, sweep, extra and metric; truncation is set to
        MINILM_MAX_TOKENS to match moss-minilm.

        Args:
            engine: Vector engine adapter to wrap.
            cache_dir: fastembed model cache directory.
        """
        from fastembed import TextEmbedding

        from bench_data import MINILM, MINILM_MAX_TOKENS

        self.engine, self.name, self.sweep, self.extra = engine, engine.name, engine.sweep, engine.extra
        self.METRICS, self.metric = engine.METRICS, engine.metric
        self.model = TextEmbedding(MINILM, cache_dir=cache_dir)
        self.model.model.tokenizer.enable_truncation(
            max_length=MINILM_MAX_TOKENS
        )  # match moss-minilm

    def open(self) -> object:
        """Forward the wrapped engine's untimed setup.

        Returns:
            Whatever the wrapped engine's open() returns (None for the synchronous engines).
        """
        return self.engine.open()

    def build(
        self, ids: np.ndarray, vectors: np.ndarray, metadata: list[dict] | None = None
    ) -> None:
        """Index the precomputed corpus vectors in the wrapped engine.

        Args:
            ids: Doc ids (corpus positions).
            vectors: Unit MiniLM corpus vectors (base_minilm.npy).
            metadata: Metadata row per doc, or None (text datasets have none).
        """
        self.engine.build(ids, vectors, metadata)

    def set_search(self, params: dict) -> None:
        """Forward the sweep setting."""
        self.engine.set_search(params)

    def search(self, q: str, k: int, flt: dict | None = None) -> list[int]:
        """Embed the query (unit-normalized), then search the wrapped engine.

        Args:
            q: Query text.
            k: Number of results.
            flt: Neutral filter, passed through, or None.

        Returns:
            Top-k doc ids, best first.
        """
        v = next(iter(self.model.embed([q])))
        return self.engine.search(v / np.linalg.norm(v), k, flt)

    def close(self) -> None:
        """Close the wrapped engine."""
        self.engine.close()


ENGINES = {
    "moss": MossEngine,
    "chroma": ChromaEngine,
    "lancedb": functools.partial(LanceEngine, "ivfpq"),  # default index: IVF_PQ
    "lancedb-hnsw": functools.partial(LanceEngine, "hnsw"),  # IVF_HNSW_SQ defaults
    "qdrant-local": QdrantLocalEngine,
    "faiss-flat": functools.partial(FaissEngine, "flat"),  # exact baseline
    "faiss-hnsw": functools.partial(FaissEngine, "hnsw"),  # IndexHNSWFlat, efSearch sweep
    "zvec": ZvecEngine,
    "sqlite-vec": SqliteVecEngine,
    "duckdb-vss": DuckdbVssEngine,
}


def make_engine(name: str, text: bool, cache_dir: str, mode: str) -> object:
    """Create the adapter for an engine, dataset kind and metric mode.

    On text datasets Moss uses its built-in model (MossTextEngine) and every other engine is wrapped
    in QueryEmbedder.

    Args:
        name: Engine name, a key of ENGINES.
        text: True for a text dataset.
        cache_dir: fastembed model cache directory (used on text datasets).
        mode: Metric mode, "default" or "ip".

    Returns:
        The engine adapter.

    Raises:
        KeyError: The engine has no such mode, or name is not a key of ENGINES.
    """
    if text and name == "moss":
        return MossTextEngine(mode)
    eng = ENGINES[name](mode)
    return QueryEmbedder(eng, cache_dir) if text else eng
