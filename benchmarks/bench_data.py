"""Fetch and prepare the standard benchmark datasets into data/<name>/ (see README.md, "Datasets").

usage: bench_data.py fetch <name>      download the raw files (resumable, sha256-checked)
       bench_data.py prepare <name>    write the prepared layout (HEAVY at 1M)
       bench_data.py subset-gt <name> <docs>
                                       exact GT over the first <docs> docs, for --docs runs
                                       (run_suite.sh runs it when needed)
       run each under the watchdog from benchmarks/, with the absolute interpreter:
       ./watchdog.sh results/logs/<step>-<name>-<stamp>.log $PWD/.venv/bin/python bench_data.py ...
names: cohere-100k (smoke), cohere-1m, dbpedia-openai-1m, arxiv-titles-2m, hotpotqa-1m, scifact

Prepared layout:
  vector datasets  base.npy (float32, unit rows), ids.npy (int64), queries.npy, gt.npy (int64
                   top-100 ids), optional labels.npy + gt_<filter>.npy, meta.json ("filters":
                   neutral filter specs)
  text dataset     corpus.jsonl ({"id": int position, "doc_id", "text"}), queries.jsonl,
                   qrels.json (keys are int positions as strings), warmup.jsonl (100 train-split
                   queries, never measured), base_minilm.npy (fastembed vectors for non-Moss
                   engines)
"""

import hashlib
import json
import subprocess
import sys
import urllib.request
from collections.abc import Callable, Iterable
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
DATA = HERE / "data"
CHECKSUMS = HERE / "checksums.json"
VDBB = "https://assets.zilliz.com/benchmark"
VDBB_FILTER_FILES = {
    "int_1p": "neighbors_head_1p",
    "int_99p": "neighbors_tail_1p",
    "label_1p": "neighbors_labels_label_1p",
    "label_50p": "neighbors_labels_label_50p",
}
HF_DBPEDIA = "KShivendu/dbpedia-entities-openai-1M"
HF_DBPEDIA_REV = "af9b8869cc2d8debbd254d77737865bb09a2067f"
MINILM = "sentence-transformers/all-MiniLM-L6-v2"  # embedder for the non-Moss engines on text data
# fastembed 0.9.0 truncates at 256 tokens by default; 512 replicates Moss's built-in text process
# exactly for vector-only search (SciFact nDCG@10 0.6541 for both; 0.6451 at 256).
MINILM_MAX_TOKENS = 512


def vdbb_files(case: str) -> dict[str, str]:
    """List the download URLs of one VectorDBBench case.

    Args:
        case: Case directory on the VectorDBBench asset host, e.g. "cohere_small_100k".

    Returns:
        File name -> URL for the base vectors, queries, ground truth, scalar labels and the ground
        truth of the four filter cases.
    """
    names = [
        "shuffle_train.parquet",
        "test.parquet",
        "neighbors.parquet",
        "scalar_labels.parquet",
    ]
    return {
        f: f"{VDBB}/{case}/{f}"
        for f in names + [f"{g}.parquet" for g in VDBB_FILTER_FILES.values()]
    }


def dbpedia_files() -> dict[str, str]:
    """List the download URLs of the 26 parquet shards of the pinned DBpedia-OpenAI-1M revision.

    The shard names come from the Hugging Face tree API (one HTTP request).

    Returns:
        Shard file name -> download URL at revision HF_DBPEDIA_REV.
    """
    url = f"https://huggingface.co/api/datasets/{HF_DBPEDIA}/tree/{HF_DBPEDIA_REV}/data"
    tree = json.load(urllib.request.urlopen(url))
    base = f"https://huggingface.co/datasets/{HF_DBPEDIA}/resolve/{HF_DBPEDIA_REV}"
    return {Path(f["path"]).name: f"{base}/{f['path']}" for f in tree}


def arxiv_files() -> dict[str, str]:
    """Return the download URL of Qdrant's arxiv-titles-384-angular (no-filters) tarball.

    Returns:
        File name -> URL (one entry).
    """
    return {
        "arxiv_no_filters.tar.gz": "https://storage.googleapis.com/ann-filtered-benchmark/datasets/arxiv_no_filters.tar.gz"
    }


def beir_files(beir_set: str) -> dict[str, str]:
    """Return the download URL of a BEIR dataset zip.

    Args:
        beir_set: BEIR dataset name, e.g. "hotpotqa" or "scifact".

    Returns:
        File name -> URL (one entry).
    """
    return {
        f"{beir_set}.zip": f"https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/{beir_set}.zip"
    }


SOURCES: dict[str, Callable[[], dict[str, str]]] = {
    "cohere-100k": lambda: vdbb_files("cohere_small_100k"),
    "cohere-1m": lambda: vdbb_files("cohere_medium_1m"),
    "dbpedia-openai-1m": dbpedia_files,
    "arxiv-titles-2m": arxiv_files,
    "hotpotqa-1m": lambda: beir_files("hotpotqa"),
    "scifact": lambda: beir_files("scifact"),
}


def sha256(path: Path) -> str:
    """Hex sha256 of a file, read in 16 MB blocks."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 24), b""):
            h.update(block)
    return h.hexdigest()


def fetch(name: str) -> None:
    """Download every raw file of a dataset into data/<name>/raw/ and check its sha256.

    A file already listed in checksums.json counts as complete and is not downloaded again; any
    other file is (re)downloaded with curl, resuming a partial download. The first fetch records
    each file's sha256 in checksums.json and later fetches verify it.

    Args:
        name: Dataset name, a key of SOURCES.

    Raises:
        SystemExit: A file's sha256 differs from the recorded one.
        subprocess.CalledProcessError: curl fails.
    """
    raw = DATA / name / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    sums = json.loads(CHECKSUMS.read_text())
    for fn, url in SOURCES[name]().items():
        dst, key = raw / fn, f"{name}/{fn}"
        if not (
            dst.exists() and key in sums
        ):  # a recorded file is complete; anything else is (re)downloaded
            subprocess.run(
                ["curl", "-fL", "--retry", "3", "-C", "-", "-o", str(dst), url],
                check=True,
            )
        digest = sha256(dst)
        if sums.get(key, digest) != digest:
            raise SystemExit(f"checksum mismatch for {key}: {digest} != {sums[key]}")
        sums[key] = digest
        CHECKSUMS.write_text(json.dumps(sums, indent=1, sort_keys=True) + "\n")
        print(f"ok {key} {digest[:12]}")


def unit(x: np.ndarray) -> np.ndarray:
    """Scale each row to unit L2 norm, as float32.

    Inner product on unit vectors equals cosine similarity, and l2 distance ranks them the same way.

    Args:
        x: Matrix with one vector per row.

    Returns:
        A new float32 matrix with unit-norm rows.
    """
    x = np.asarray(x, dtype=np.float32)
    return x / np.linalg.norm(x, axis=1, keepdims=True)


def exact_topk(base: np.ndarray, queries: np.ndarray, k: int = 100, chunk: int = 256) -> np.ndarray:
    """Find the exact top-k rows of base for each query by inner product (brute force).

    Queries are scored `chunk` at a time, so the score matrix in memory is chunk x n_base.

    Args:
        base: Doc vectors, one per row.
        queries: Query vectors, one per row.
        k: Number of neighbors per query.
        chunk: Queries scored per matrix product.

    Returns:
        Row indices into base, shape (n_queries, k), int64, best first.
    """
    out = np.empty((len(queries), k), dtype=np.int64)
    for i in range(0, len(queries), chunk):
        s = queries[i : i + chunk] @ base.T
        top = np.argpartition(-s, k - 1, axis=1)[:, :k]
        order = np.argsort(-np.take_along_axis(s, top, axis=1), axis=1, kind="stable")
        out[i : i + chunk] = np.take_along_axis(top, order, axis=1)
    return out


def check_docs(docs: int, n_base: int) -> None:
    """Refuse a doc subset that is not a proper prefix of the corpus.

    Args:
        docs: Requested number of docs (--docs).
        n_base: Docs in the full dataset.

    Raises:
        SystemExit: docs is not between 1 and n_base - 1 (a full run covers all docs).
    """
    if not 0 < docs < n_base:
        raise SystemExit(
            f"--docs must be between 1 and {n_base - 1}; a full run covers all {n_base}"
        )


def subset_gt_path(name: str, docs: int) -> Path:
    """Path of the cached exact top-100 ground truth over the first `docs` docs of a dataset.

    Args:
        name: Dataset name.
        docs: Number of leading docs.

    Returns:
        data/<name>/gt_docs<docs>.npy.
    """
    return DATA / name / f"gt_docs{docs}.npy"


def subset_gt(name: str, docs: int) -> None:
    """Write the exact top-100 doc ids of every query over the first `docs` docs (--docs runs).

    Computed in its own process because the brute-force temporaries (chunk x docs scores) stay
    counted in the process footprint after they are freed; computing them inside run.py inflated
    its memory baseline (up to 440 MB at 75k docs). run.py slices the rows for --queries (each
    row depends only on its own query).

    Args:
        name: Vector dataset name; data/<name>/ must be prepared.
        docs: Number of leading docs.

    Raises:
        SystemExit: A text dataset, or docs outside 1..n_base - 1.
    """
    d = load(name)
    if d["meta"]["kind"] != "vector":
        raise SystemExit("subset-gt applies to vector datasets only")
    check_docs(docs, d["meta"]["n_base"])
    top = exact_topk(np.asarray(d["base"][:docs]), d["queries"], min(100, docs))
    np.save(subset_gt_path(name, docs), d["ids"][:docs][top])
    print(f"{name}: wrote {subset_gt_path(name, docs)} {top.shape}")


def select_subset(corpus_ids: Iterable[str], required: set[str], size: int) -> set[str]:
    """Choose up to size docs, keeping every qrel doc (VectorDBBench _build_selected_doc_ids).

    Every required doc is kept and the rest of the budget is filled with docs in corpus order. The
    scan stops once the budget is full and every required doc has been seen.

    Args:
        corpus_ids: Doc ids in corpus order (iterated once).
        required: Doc ids that must be kept (those with a qrel).
        size: Maximum number of docs.

    Returns:
        The selected doc ids.

    Raises:
        ValueError: There are more required docs than size, or required docs are missing from the
            corpus.
    """
    if len(required) > size:
        raise ValueError(f"size={size} is too small for {len(required)} qrel documents")
    selected, found = set(required), set()
    for d in corpus_ids:
        if d in required:
            found.add(d)
        if d not in selected and len(selected) < size:
            selected.add(d)
        if len(selected) >= size and found == required:
            break
    if required - found:
        raise ValueError(f"{len(required - found)} qrel docs missing from corpus")
    return selected


def save(name: str, meta: dict, **arrays: np.ndarray) -> None:
    """Write a prepared dataset's arrays and metadata to data/<name>/.

    Args:
        name: Dataset name; data/<name>/ must already exist.
        meta: Metadata, written to meta.json.
        **arrays: Arrays to write, each as <key>.npy.
    """
    out = DATA / name
    for key, arr in arrays.items():
        np.save(out / f"{key}.npy", arr)
    (out / "meta.json").write_text(json.dumps(meta, indent=1) + "\n")


def load(name: str) -> dict:
    """Load a prepared dataset from data/<name>/.

    Base vectors are memory-mapped, so builds never copy them whole.

    Args:
        name: Dataset name.

    Returns:
        For a vector dataset: meta, base, ids, queries, gt and, when it has labels, labels and
        gt_filters (filter tag -> ground truth). For a text dataset: meta, corpus and queries_text
        (lists of JSON rows), warmup_text (warmup.jsonl rows, or None), base (the MiniLM vectors,
        or None before embedding), ids (corpus positions) and qrels.
    """
    out = DATA / name
    meta = json.loads((out / "meta.json").read_text())
    if meta["kind"] == "text":
        corpus = [json.loads(line) for line in (out / "corpus.jsonl").open()]
        queries = [json.loads(line) for line in (out / "queries.jsonl").open()]
        vecs = (
            np.load(out / "base_minilm.npy", mmap_mode="r")
            if (out / "base_minilm.npy").exists()
            else None
        )
        warm = out / "warmup.jsonl"
        return {
            "meta": meta,
            "corpus": corpus,
            "queries_text": queries,
            "warmup_text": [json.loads(line) for line in warm.open()] if warm.exists() else None,
            "base": vecs,
            "ids": np.arange(len(corpus), dtype=np.int64),
            "qrels": json.loads((out / "qrels.json").read_text()),
        }
    d = {
        "meta": meta,
        "base": np.load(out / "base.npy", mmap_mode="r"),
        "ids": np.load(out / "ids.npy"),
        "queries": np.load(out / "queries.npy"),
        "gt": np.load(out / "gt.npy"),
    }
    if (out / "labels.npy").exists():
        d["labels"] = np.load(out / "labels.npy")
        d["gt_filters"] = {t: np.load(out / f"gt_{t}.npy") for t in meta["filters"]}
    return d


def _parquet_matrix(path: Path, col: str) -> tuple[np.ndarray, np.ndarray]:
    """Read the ids and a list-valued column of a parquet file, sorted by id.

    Args:
        path: Parquet file with an `id` column.
        col: List column holding one vector per row.

    Returns:
        The ids and a matrix with one row per id.
    """
    import pyarrow.parquet as pq

    t = pq.read_table(path).sort_by("id")
    flat = np.asarray(t.column(col).combine_chunks().flatten())
    return t.column("id").to_numpy(), flat.reshape(t.num_rows, -1)


def _gt_matrix(path: Path, k: int = 100) -> np.ndarray:
    """Read a VectorDBBench neighbors file as a top-k id matrix, sorted by query id.

    Rows can be ragged (filtered cases may list fewer neighbors); short rows are padded with -1,
    which never matches a doc.

    Args:
        path: Neighbors parquet file with `id` and `neighbors_id` columns.
        k: Neighbors kept per query.

    Returns:
        Neighbor ids, shape (n_queries, k), int64.
    """
    import pyarrow.parquet as pq

    rows = pq.read_table(path).sort_by("id").column("neighbors_id").to_pylist()
    out = np.full((len(rows), k), -1, dtype=np.int64)
    for i, r in enumerate(rows):
        out[i, : min(k, len(r))] = r[:k]
    return out


def prepare_vdbb(name: str) -> None:
    """Prepare a VectorDBBench Cohere case: unit vectors, top-100 GT, labels and filter cases.

    The ground truth, plain and per filter case, is VectorDBBench's own. Filter semantics follow
    VDBB backend/filter.py: IntFilter keeps id >= int(size * rate) (head_1p = rate 0.01, tail_1p =
    rate 0.99); LabelFilter keeps labels == "label_<p>p".

    Args:
        name: Dataset name (cohere-100k or cohere-1m); reads data/<name>/raw/.
    """
    import pyarrow.parquet as pq

    raw = DATA / name / "raw"
    ids, base = _parquet_matrix(raw / "shuffle_train.parquet", "emb")
    _, queries = _parquet_matrix(raw / "test.parquet", "emb")
    gt = {"gt": _gt_matrix(raw / "neighbors.parquet")}
    for tag, fn in VDBB_FILTER_FILES.items():
        gt[f"gt_{tag}"] = _gt_matrix(raw / f"{fn}.parquet")
    lab = pq.read_table(raw / "scalar_labels.parquet").to_pydict()
    by_id = dict(zip(lab["id"], lab["labels"]))
    n = len(ids)
    filters = {
        "int_1p": {"field": "id", "op": "gte", "value": int(n * 0.01)},
        "int_99p": {"field": "id", "op": "gte", "value": int(n * 0.99)},
        "label_1p": {"field": "labels", "op": "eq", "value": "label_1p"},
        "label_50p": {"field": "labels", "op": "eq", "value": "label_50p"},
    }
    meta = {
        "name": name,
        "kind": "vector",
        "metric": "cosine",
        "dim": base.shape[1],
        "n_base": n,
        "n_queries": len(queries),
        "gt_k": 100,
        "filters": filters,
        "source": SOURCES[name](),
    }
    save(
        name,
        meta,
        base=unit(base),
        ids=ids.astype(np.int64),
        queries=unit(queries),
        labels=np.array([by_id[i] for i in ids.tolist()]),
        **gt,
    )
    print(f"{name}: base {base.shape}, queries {queries.shape}, labels {len(by_id)}")


def prepare_dbpedia(name: str) -> None:
    """Prepare DBpedia-OpenAI-1M with the ann-benchmarks split and exact top-100 GT.

    ann-benchmarks dbpedia_entities_openai_1M calls train_test_split(embeddings, test_size=10_000,
    random_state=42) on the HF rows in shard order; sklearn's shuffle depends only on (n,
    random_state), so splitting np.arange(n) yields the same partition. Doc ids are the HF row
    indices.

    Args:
        name: Dataset name (dbpedia-openai-1m); reads the 26 shards in data/<name>/raw/.
    """
    import pyarrow.parquet as pq
    from sklearn.model_selection import train_test_split

    shards = sorted((DATA / name / "raw").glob("train-*.parquet"))
    assert len(shards) == 26, shards
    x = np.concatenate(
        [
            np.asarray(
                pq.read_table(s, columns=["openai"]).column("openai").combine_chunks().flatten(),
                dtype=np.float32,
            ).reshape(-1, 1536)
            for s in shards
        ]
    )
    assert x.shape == (1_000_000, 1536), x.shape
    train, test = train_test_split(np.arange(len(x)), test_size=10_000, random_state=42)
    base, queries = unit(x[train]), unit(x[test])
    del x
    gt = train[exact_topk(base, queries, 100)]
    meta = {
        "name": name,
        "kind": "vector",
        "metric": "angular",
        "dim": 1536,
        "n_base": len(base),
        "n_queries": len(queries),
        "gt_k": 100,
        "filters": {},
        "source": {"hf": HF_DBPEDIA, "revision": HF_DBPEDIA_REV},
    }
    save(name, meta, base=base, ids=train.astype(np.int64), queries=queries, gt=gt)
    print(f"{name}: base {base.shape}, queries {queries.shape}")


def prepare_arxiv(name: str) -> None:
    """Prepare Qdrant's arxiv-titles (all-MiniLM-L6-v2 vectors) with exact top-100 GT.

    The tarball is extracted once. The computed top-10 is cross-checked against Qdrant's
    closest_ids; doc ids are row positions.

    Args:
        name: Dataset name (arxiv-titles-2m); reads data/<name>/raw/.

    Raises:
        SystemExit: Top-10 agreement with Qdrant's closest_ids is below 0.99 (wrong id mapping or
            metric).
    """
    import tarfile

    raw = DATA / name / "raw"
    ext = raw / "extracted"
    if not ext.exists():
        with tarfile.open(raw / "arxiv_no_filters.tar.gz") as tf:
            tf.extractall(ext, filter="data")
    base = unit(np.load(next(ext.rglob("vectors.npy"))))
    tests = [json.loads(line) for line in next(ext.rglob("tests.jsonl")).open()]
    queries = unit(np.array([t["query"] for t in tests], dtype=np.float32))
    gt = exact_topk(base, queries, 100)
    agree = float(
        np.mean([len(set(g[:10].tolist()) & set(t["closest_ids"])) / 10 for g, t in zip(gt, tests)])
    )
    print(f"top-10 agreement with Qdrant closest_ids: {agree:.4f}")
    if agree < 0.99:
        raise SystemExit("ground truth disagrees with Qdrant's; the id mapping or metric is wrong")
    meta = {
        "name": name,
        "kind": "vector",
        "metric": "cosine",
        "dim": 384,
        "n_base": len(base),
        "n_queries": len(queries),
        "gt_k": 100,
        "filters": {},
        "qdrant_top10_agreement": agree,
        "source": arxiv_files(),
    }
    save(
        name,
        meta,
        base=base,
        ids=np.arange(len(base), dtype=np.int64),
        queries=queries,
        gt=gt,
    )
    print(f"{name}: base {base.shape}, queries {queries.shape}")


def prepare_beir(name: str, beir_set: str = "hotpotqa", size: int = 1_000_000) -> None:
    """Prepare a BEIR text dataset capped at `size` docs, with MiniLM vectors for other engines.

    Reads data/<name>/raw/<beir_set>.zip and keeps the test-split qrels with a grade above 0. The
    corpus is capped with VectorDBBench's qrel-preserving rule (select_subset). Doc text follows
    VDBB HotpotQATranslator: f"{title} {text}" with tabs/newlines replaced by spaces. Docs get
    integer ids = position in corpus.jsonl and the qrels are re-keyed to those positions. Writes
    corpus.jsonl, queries.jsonl (queries with qrels only), qrels.json, meta.json and warmup.jsonl
    (write_warmup), then runs embed_corpus().

    Args:
        name: Dataset name; output goes to data/<name>/.
        beir_set: BEIR dataset name, the zip's top-level directory.
        size: Maximum number of corpus docs.
    """
    import csv
    import io
    import zipfile

    out = DATA / name
    with zipfile.ZipFile(out / "raw" / f"{beir_set}.zip") as z:
        qrels_raw: dict[str, dict[str, int]] = {}
        with z.open(f"{beir_set}/qrels/test.tsv") as f:
            for row in csv.DictReader(io.TextIOWrapper(f), delimiter="\t"):
                if int(row["score"]) > 0:
                    qrels_raw.setdefault(row["query-id"], {})[row["corpus-id"]] = int(row["score"])
        required = {d for rels in qrels_raw.values() for d in rels}
        with z.open(f"{beir_set}/corpus.jsonl") as f:
            keep = select_subset((json.loads(line)["_id"] for line in f), required, size)
        pos: dict[str, int] = {}
        with (
            z.open(f"{beir_set}/corpus.jsonl") as f,
            (out / "corpus.jsonl").open("w") as w,
        ):
            for line in f:
                d = json.loads(line)
                if d["_id"] in keep:
                    text = (
                        f"{d.get('title') or ''} {d.get('text') or ''}".replace("\t", " ")
                        .replace("\n", " ")
                        .strip()
                    )
                    pos[d["_id"]] = len(pos)
                    w.write(
                        json.dumps({"id": pos[d["_id"]], "doc_id": d["_id"], "text": text}) + "\n"
                    )
        with (
            z.open(f"{beir_set}/queries.jsonl") as f,
            (out / "queries.jsonl").open("w") as w,
        ):
            for line in f:
                q = json.loads(line)
                if q["_id"] in qrels_raw:
                    w.write(json.dumps({"id": q["_id"], "text": q["text"]}) + "\n")
    qrels = {q: {str(pos[d]): r for d, r in rels.items()} for q, rels in qrels_raw.items()}
    (out / "qrels.json").write_text(json.dumps(qrels))
    meta = {
        "name": name,
        "kind": "text",
        "n_base": len(pos),
        "n_queries": len(qrels),
        "required_qrel_docs": len(required),
        "embedder_for_other_engines": MINILM,
        "source": f"BEIR {beir_set} (test split)",
    }
    (out / "meta.json").write_text(json.dumps(meta, indent=1) + "\n")
    print(f"{name}: corpus {len(pos)}, queries {len(qrels)}, qrel docs {len(required)}")
    write_warmup(name, beir_set)
    embed_corpus(name)


def write_warmup(name: str, beir_set: str, n: int = 100) -> None:
    """Write warmup.jsonl: the first n train-split queries that are not test queries.

    run.py warms each engine up on these before measuring, so the warm-up queries come from the
    same distribution as the measured (test) queries but are never measured themselves.

    Args:
        name: Dataset name; reads data/<name>/raw/<beir_set>.zip, writes data/<name>/warmup.jsonl.
        beir_set: BEIR dataset name, the zip's top-level directory.
        n: Number of warm-up queries.
    """
    import csv
    import io
    import zipfile

    out = DATA / name
    with zipfile.ZipFile(out / "raw" / f"{beir_set}.zip") as z:

        def ids(split: str) -> set[str]:
            with z.open(f"{beir_set}/qrels/{split}.tsv") as f:
                return {
                    row["query-id"] for row in csv.DictReader(io.TextIOWrapper(f), delimiter="\t")
                }

        train = ids("train") - ids("test")
        rows = []
        with z.open(f"{beir_set}/queries.jsonl") as f:
            for line in f:
                q = json.loads(line)
                if q["_id"] in train and len(rows) < n:
                    rows.append({"id": q["_id"], "text": q["text"]})
    if len(rows) < n:
        raise SystemExit(f"{name}: only {len(rows)} train queries for warm-up, need {n}")
    (out / "warmup.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    print(f"{name}: wrote {n} train-split warm-up queries")


def embed_corpus(name: str, batch: int = 256) -> None:
    """Embed corpus.jsonl with fastembed MiniLM into base_minilm.npy for the non-Moss engines.

    Truncation is set to MINILM_MAX_TOKENS (see its comment). Vectors are
    unit-normalized and written row by row to a memory-mapped file; the embedding time is added to
    meta.json as corpus_embed_s.

    Args:
        name: Dataset name; reads and writes data/<name>/.
        batch: Texts per fastembed batch.
    """
    import time

    from fastembed import TextEmbedding

    texts = [json.loads(line)["text"] for line in (DATA / name / "corpus.jsonl").open()]
    model = TextEmbedding(MINILM, cache_dir=str(DATA / ".fastembed"))
    model.model.tokenizer.enable_truncation(max_length=MINILM_MAX_TOKENS)
    out = np.lib.format.open_memmap(
        DATA / name / "base_minilm.npy",
        mode="w+",
        dtype=np.float32,
        shape=(len(texts), 384),
    )
    t0 = time.perf_counter()
    for i, v in enumerate(model.embed(texts, batch_size=batch)):
        out[i] = v / np.linalg.norm(v)
    out.flush()
    meta_path = DATA / name / "meta.json"
    meta = json.loads(meta_path.read_text()) | {"corpus_embed_s": time.perf_counter() - t0}
    meta_path.write_text(json.dumps(meta, indent=1) + "\n")
    print(f"{name}: embedded {len(texts)} docs in {meta['corpus_embed_s']:.0f}s")


PREPARE: dict[str, Callable[[str], None]] = {
    "cohere-100k": prepare_vdbb,
    "cohere-1m": prepare_vdbb,
    "dbpedia-openai-1m": prepare_dbpedia,
    "arxiv-titles-2m": prepare_arxiv,
    "hotpotqa-1m": prepare_beir,  # defaults: BEIR hotpotqa, 1M docs
    "scifact": lambda name: prepare_beir(name, "scifact", 10_000),  # all 5,183 docs
}

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd not in ("fetch", "prepare", "subset-gt") or len(sys.argv) != (
        4 if cmd == "subset-gt" else 3
    ):
        raise SystemExit(__doc__)  # a typo must not start the heavy prepare
    name = sys.argv[2]
    if cmd != "subset-gt" and name not in SOURCES:  # fetch / prepare index SOURCES and PREPARE
        raise SystemExit(f"unknown dataset {name}; choose from {', '.join(SOURCES)}")
    if cmd == "fetch":
        fetch(name)
    elif cmd == "prepare":
        PREPARE[name](name)
    else:
        subset_gt(name, int(sys.argv[3]))  # any prepared vector dataset
