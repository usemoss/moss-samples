import asyncio
import json
import math
import statistics
import time
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as pkg_version
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import pytest

from moss import DocumentInfo, MossClient, QueryOptions, SearchResult

from .constants import TEST_PROJECT_ID, TEST_PROJECT_KEY

# ------------------- Configuration -------------------

EMBEDDING_MODEL = "moss-minilm"


# Interface for Experiment Configuration
@dataclass
class ExperimentConfig:
    name: str
    dataset_path: Path
    alpha: Optional[float]
    top_k: int = 10


# Interface for Run Statistics
@dataclass
class RunStats:
    experiment: str
    sdk_version: str
    dataset_name: str
    num_queries: int
    hit_rate: Optional[float]
    mrr: Optional[float]
    ndcg: Optional[float]
    avg_latency_ms: Optional[float]
    p95_latency_ms: Optional[float]
    error_reason: Optional[str] = None


# Dataclass for Caching the dataset to avoid re-loading
@dataclass
class DatasetCache:
    """Cache for dataset data to avoid re-loading across experiments."""

    dataset_path: Optional[Path] = None
    qrels: Optional[Dict[str, Dict[str, float]]] = None
    queries: Optional[Dict[str, str]] = None


# -------------------- Data Loaders --------------------


# Loads the corpus from the corpus.jsonl file and combines the title and text into a single string
def load_corpus(path: Path) -> List[DocumentInfo]:
    """Loads the entire mini-corpus into memory at once."""
    if not path.exists():
        pytest.skip(f"File not found: {path}")

    print(f"Loading docs from {path.name}...")
    docs = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            data = json.loads(line)
            # Combine title + text for best search results
            text = (
                str(data.get("title", "")) + " " + str(data.get("text", ""))
            ).strip()
            docs.append(DocumentInfo(id=str(data["_id"]), text=text, metadata={}))
    print(f"   Loaded {len(docs)} documents.")
    return docs


# -------- Loads the qrels from the qrels/test.tsv file --------
# Example struct of qrels : {"query-id": {"doc-id": score}}
def load_qrels(path: Path) -> Dict[str, Dict[str, float]]:
    """Loads relevance (Query ID -> Doc ID -> Score)."""
    if not path.exists():
        pytest.skip(f"Qrels file not found: {path}")

    # Cache file path
    cache_path = path.parent / f"{path.stem}_cache.json"

    # Check if cache exists and is newer than source file
    if cache_path.exists():
        cache_mtime = cache_path.stat().st_mtime
        source_mtime = path.stat().st_mtime
        if cache_mtime >= source_mtime:

            # Load from cache
            print(f"Loading qrels from cache: {cache_path.name}...")
            with cache_path.open("r", encoding="utf-8") as f:
                qrels = json.load(f)
                qrels = {
                    qid: {did: float(score) for did, score in docs.items()}
                    for qid, docs in qrels.items()
                }
            print(f"   Loaded {len(qrels)} query judgments from cache.")
            return qrels

    # Parse from source file
    print(f"Loading qrels from {path.name}...")
    qrels = {}
    with path.open("r", encoding="utf-8") as f:
        # Check/Skip header
        pos = f.tell()
        header_line = f.readline()
        if "query-id" not in header_line.lower():
            f.seek(pos)

        for line in f:
            parts = line.strip().split()
            if len(parts) >= 3:
                qid, did, score = parts[0], parts[1], float(parts[2])
                qrels.setdefault(qid, {})[did] = score

    # Save to cache
    print(f"   Caching qrels to {cache_path.name}...")
    with cache_path.open("w", encoding="utf-8") as f:
        json.dump(qrels, f, indent=2)
    print(f"   Loaded {len(qrels)} query judgments.")

    return qrels


# -------- Loads the queries from the queries.jsonl --------
# Example struct of queries : {"_id": "text"}
def load_queries(path: Path, valid_qids: Set[str]) -> Dict[str, str]:
    """Loads queries that exist in the Qrels."""
    queries = {}
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            data = json.loads(line)
            qid = str(data["_id"])
            if qid in valid_qids:
                queries[qid] = str(data["text"])
    return queries


# -------------------- Metrics Utils --------------------


# -------- Calculates the NDCG metric --------
# NDCG (Normalized Discounted Cumulative Gain) measures ranking quality by considering
# both relevance and position. Higher positions and higher relevance scores contribute more.
#
# Formula: NDCG@k = DCG@k / IDCG@k
# - DCG@k = Σ(i=0 to k-1) (2^rel_i - 1) / log2(i + 2)
#   * Sums relevance gains (2^rel - 1) discounted by position (log2(i+2))
# - IDCG@k = DCG of the ideal ranking (documents sorted by relevance descending)
# - Result: Score between 0.0 (worst) and 1.0 (perfect ranking)
def calculate_ndcg(
    retrieved_ids: List[str], true_rels: Dict[str, float], k: int
) -> float:
    dcg = 0.0
    idcg = 0.0

    # 1. DCG
    for i, doc_id in enumerate(retrieved_ids[:k]):
        rel = true_rels.get(doc_id, 0)
        if rel > 0:
            dcg += (2**rel - 1) / math.log2(i + 2)

    # 2. IDCG (Ideal ordering)
    ideal_scores = sorted(true_rels.values(), reverse=True)[:k]
    for i, rel in enumerate(ideal_scores):
        idcg += (2**rel - 1) / math.log2(i + 2)

    return (dcg / idcg) if idcg > 0 else 0.0


# -------------------- Core Execution --------------------
# Run a single experiment scenario, based on the provided config
async def run_scenario(
    client: MossClient,
    config: ExperimentConfig,
    queries: Dict,
    qrels: Dict,
    index_name: str,
) -> RunStats:
    print(
        f"\nRunning Experiment: {config.name} (alpha={config.alpha}, dataset={config.dataset_path.name}) \n"
    )

    latencies = []
    hits = 0
    mrr_sum = 0.0
    ndcg_sum = 0.0

    try:
        current_sdk_version = pkg_version("moss")
    except PackageNotFoundError:
        current_sdk_version = "unknown"

    for qid, text in queries.items():
        # 1. Search
        options = QueryOptions(top_k=config.top_k, alpha=config.alpha)
        res: SearchResult = await client.query(index_name, text, options)

        # 2. Latency Measurement
        latencies.append(res.time_taken_ms)

        # 3. Score
        retrieved_ids = [d.id for d in res.docs]
        relevant_docs = qrels.get(qid, {})

        # Check Hit & MRR
        is_hit = False
        for rank, doc_id in enumerate(retrieved_ids, 1):
            if doc_id in relevant_docs:
                if not is_hit:
                    hits += 1
                    mrr_sum += 1.0 / rank
                    is_hit = True

        # Check NDCG
        ndcg_sum += calculate_ndcg(retrieved_ids, relevant_docs, config.top_k)

    count = len(queries)
    return RunStats(
        experiment=config.name,
        sdk_version=current_sdk_version,
        dataset_name=config.dataset_path.name,
        num_queries=count,
        hit_rate=hits / count,
        mrr=mrr_sum / count,
        ndcg=ndcg_sum / count,
        avg_latency_ms=statistics.mean(latencies),
        p95_latency_ms=(
            sorted(latencies)[int(len(latencies) * 0.95)]
            if len(latencies) >= 2
            else float("nan")
        ),
    )


async def main():
    print("\n==========================================")
    print(" MOSS BENCHMARK: Multi-Dataset Testing")
    print("==========================================\n")

    client = MossClient(TEST_PROJECT_ID, TEST_PROJECT_KEY)

    # Define the base dataset path dynamically
    BASE_DATASET_PATH = Path(__file__).resolve().parents[3] / "test-dataset"

    # 1. Define Experiments
    experiments = [
        ExperimentConfig(
            "Keyword Search(alpha=0)",
            dataset_path=BASE_DATASET_PATH / "full_scifact",
            alpha=0,
        ),
        ExperimentConfig(
            "Keyword Search(alpha=0)",
            dataset_path=BASE_DATASET_PATH / "full_nfcorpus",
            alpha=0,
        ),
        ExperimentConfig(
            "Keyword Search(alpha=0)",
            dataset_path=BASE_DATASET_PATH / "mini_msmarco",
            alpha=0,
        ),
        ExperimentConfig(
            "Fusion Search(alpha=0.2)",
            dataset_path=BASE_DATASET_PATH / "full_scifact",
            alpha=0.2,
        ),
        ExperimentConfig(
            "Fusion Search(alpha=0.2)",
            dataset_path=BASE_DATASET_PATH / "full_nfcorpus",
            alpha=0.2,
        ),
        ExperimentConfig(
            "Fusion Search(alpha=0.2)",
            dataset_path=BASE_DATASET_PATH / "mini_msmarco",
            alpha=0.2,
        ),
        ExperimentConfig(
            "Fusion Search(alpha=0.4)",
            dataset_path=BASE_DATASET_PATH / "full_scifact",
            alpha=0.4,
        ),
        ExperimentConfig(
            "Fusion Search(alpha=0.4)",
            dataset_path=BASE_DATASET_PATH / "full_nfcorpus",
            alpha=0.4,
        ),
        ExperimentConfig(
            "Fusion Search(alpha=0.4)",
            dataset_path=BASE_DATASET_PATH / "mini_msmarco",
            alpha=0.4,
        ),
        ExperimentConfig(
            "Fusion Search(alpha=0.6)",
            dataset_path=BASE_DATASET_PATH / "full_scifact",
            alpha=0.6,
        ),
        ExperimentConfig(
            "Fusion Search(alpha=0.6)",
            dataset_path=BASE_DATASET_PATH / "full_nfcorpus",
            alpha=0.6,
        ),
        ExperimentConfig(
            "Fusion Search(alpha=0.6)",
            dataset_path=BASE_DATASET_PATH / "mini_msmarco",
            alpha=0.6,
        ),
        ExperimentConfig(
            "Fusion Search(alpha=0.8)",
            dataset_path=BASE_DATASET_PATH / "full_scifact",
            alpha=0.8,
        ),
        ExperimentConfig(
            "Fusion Search(alpha=0.8)",
            dataset_path=BASE_DATASET_PATH / "full_nfcorpus",
            alpha=0.8,
        ),
        ExperimentConfig(
            "Fusion Search(alpha=0.8)",
            dataset_path=BASE_DATASET_PATH / "mini_msmarco",
            alpha=0.8,
        ),
        ExperimentConfig(
            "Embedding Search(alpha=1)",
            dataset_path=BASE_DATASET_PATH / "full_scifact",
            alpha=1,
        ),
        ExperimentConfig(
            "Embedding Search(alpha=1)",
            dataset_path=BASE_DATASET_PATH / "full_nfcorpus",
            alpha=1,
        ),
        ExperimentConfig(
            "Embedding Search(alpha=1)",
            dataset_path=BASE_DATASET_PATH / "mini_msmarco",
            alpha=1,
        ),
    ]

    # 2. Sort experiments by dataset to minimize I/O
    experiments = sorted(experiments, key=lambda e: e.dataset_path)

    # ---------------------------------------------------------
    # PHASE 1: INDEX PREPARATION (Delete -> Create)
    # ---------------------------------------------------------
    # Identify all unique datasets required by the experiments
    unique_dataset_paths = sorted(list({exp.dataset_path for exp in experiments}))

    # Map dataset paths to their created index names
    dataset_to_index_map: Dict[Path, str] = {}
    failed_datasets: Dict[Path, Dict[str, Any]] = {}

    # Get current version for safe index naming
    try:
        current_sdk_version = pkg_version("moss")
    except PackageNotFoundError:
        current_sdk_version = "unknown"
    safe_version = current_sdk_version.replace(".", "_").replace("-", "_")

    print(
        f"\n🚀 PRE-COMPUTING INDICES for {len(unique_dataset_paths)} unique datasets..."
    )

    for dpath in unique_dataset_paths:
        corpus_path = dpath / "corpus.jsonl"
        if not corpus_path.exists():
            print(f"❌ Skipping index creation: Missing corpus at {dpath.name}")
            continue

        # 1. Construct Unique Index Name
        index_name = f"{dpath.name}_{safe_version}_index"
        # 2. Load Corpus (Only needed for creation, then we can free memory)
        print(f"\nProcessing {dpath.name}...")
        docs = load_corpus(corpus_path)

        # 3. Force Delete Existing Index
        print(f"   🗑️  Cleaning old index: {index_name}...")
        try:
            # Assuming delete_index is the API method.
            # Wrap in try/except in case it throws an error if index doesn't exist.
            await client.delete_index(index_name)
        except Exception:
            # It's fine if it fails because it didn't exist
            pass

        # 4. Create Fresh Index
        print(f"   ✨ Creating fresh index: {index_name}...")
        t0 = time.time()
        skip_reason: Optional[str] = None
        try:
            success = await client.create_index(index_name, docs, EMBEDDING_MODEL)
        except Exception as exc:
            error_message = str(exc)
            if "HTTP error! status: 400" in error_message:
                skip_reason = "Cloud API rejected dataset error(400): payload failed validation or field limits"
                failed_datasets[dpath] = {
                    "reason": skip_reason,
                    "index_name": index_name,
                }
                print(f"   ⚠️  {skip_reason}")
            elif "HTTP error! status: 413" in error_message:
                skip_reason = "Cloud API rejected dataset error(413): payload size exceeds server maximum"
                failed_datasets[dpath] = {
                    "reason": skip_reason,
                    "index_name": index_name,
                }
                print(f"   ⚠️  {skip_reason}")
            elif "HTTP error! status: 500" in error_message:
                skip_reason = "Cloud API server error(500): internal server error during index creation"
                failed_datasets[dpath] = {
                    "reason": skip_reason,
                    "index_name": index_name,
                }
                print(f"   ⚠️  {skip_reason}")
            elif "Cloud API request failed" in error_message:
                skip_reason = "Cloud API request failed"
                failed_datasets[dpath] = {
                    "reason": skip_reason,
                    "index_name": index_name,
                }
                print(f"   ⚠️  {skip_reason}")
            else:
                raise
        finally:
            # Free memory immediately (we don't need raw text for querying, only IDs/Scores)
            del docs

        if skip_reason:
            continue

        if not success:
            print(f"   ❌ Failed to create index for {dpath.name}")
            continue

        dataset_to_index_map[dpath] = index_name
        print(f"   ✅ Created in {time.time()-t0:.2f}s")

    # ---------------------------------------------------------
    # PHASE 2: EXPERIMENT EXECUTION (Load -> Query)
    # ---------------------------------------------------------
    print("\n" + "=" * 60)
    print(" STARTING EXPERIMENTS")
    print("=" * 60)

    results = []
    dataset_cache = DatasetCache()

    for exp in experiments:
        # Check if we have a valid index for this dataset
        if exp.dataset_path in failed_datasets:
            failure_info = failed_datasets[exp.dataset_path]
            reason = failure_info.get("reason", "Index creation failed")
            results.append(
                RunStats(
                    experiment=exp.name,
                    sdk_version=current_sdk_version,
                    dataset_name=exp.dataset_path.name,
                    num_queries=0,
                    hit_rate=None,
                    mrr=None,
                    ndcg=None,
                    avg_latency_ms=None,
                    p95_latency_ms=None,
                    error_reason=reason,
                )
            )
            continue

        if exp.dataset_path not in dataset_to_index_map:
            print(
                f"Skipping {exp.name}: Index was not created during the preparation phase for {exp.dataset_path.name}"
            )
            continue

        index_name = dataset_to_index_map[exp.dataset_path]

        # ----- Manage Data Cache (Qrels/Queries) -----
        # We only reload qrels/queries if the dataset changes
        if exp.dataset_path != dataset_cache.dataset_path:
            qrels_path = exp.dataset_path / "qrels.tsv"
            queries_path = exp.dataset_path / "queries.jsonl"

            if not qrels_path.exists() or not queries_path.exists():
                print(f"Skipping {exp.name}: Missing qrels/queries")
                continue

            print(f"\n📂 Loading test data for: {exp.dataset_path.name}")
            dataset_cache.qrels = load_qrels(qrels_path)
            dataset_cache.queries = load_queries(
                queries_path, set(dataset_cache.qrels.keys())
            )
            dataset_cache.dataset_path = exp.dataset_path

            # CRITICAL STEP: Load the index specifically for this dataset
            print(f"🔌 Connecting to index: {index_name}")
            try:
                await client.load_index(index_name)
            except Exception as exc:
                if "Cloud API request failed" in str(exc):
                    reason = "Cloud API request failed"
                else:
                    raise
                failed_datasets[exp.dataset_path] = {
                    "reason": reason,
                    "index_name": index_name,
                }
                results.append(
                    RunStats(
                        experiment=exp.name,
                        sdk_version=current_sdk_version,
                        dataset_name=exp.dataset_path.name,
                        num_queries=0,
                        hit_rate=None,
                        mrr=None,
                        ndcg=None,
                        avg_latency_ms=None,
                        p95_latency_ms=None,
                        error_reason=reason,
                    )
                )
                continue

        # ----- Run Experiment -----
        stats = await run_scenario(
            client, exp, dataset_cache.queries, dataset_cache.qrels, index_name
        )
        results.append(stats)

    # ---------------------------------------------------------
    # PHASE 3: REPORTING
    # ---------------------------------------------------------

    # Print Table
    header = f"{'Experiment':<25} | {'SDK Version':<12} | {'Dataset':<30} | {'HitRate':>8} | {'NDCG':>8} | {'MRR':>8} | {'Avg(ms)':>8} | {'P95(ms)':>8} | {'Reason':<40}"
    separator = "=" * len(header)
    print("\n" + separator)
    print(" EXPERIMENT RESULTS")
    print(separator)
    print(header)
    print("-" * len(header))

    for stats in results:
        if stats.error_reason:
            print(
                f"{stats.experiment:<25} | {stats.sdk_version:<12} | {stats.dataset_name:<30} | {'N/A':>8} | {'N/A':>8} | {'N/A':>8} | {'N/A':>8} | {'N/A':>8} | {stats.error_reason:<40}"
            )
        else:
            print(
                f"{stats.experiment:<25} | {stats.sdk_version:<12} | {stats.dataset_name:<30} | {stats.hit_rate:>8.3f} | {stats.ndcg:>8.3f} | {stats.mrr:>8.3f} | {stats.avg_latency_ms:>8.1f} | {stats.p95_latency_ms:>8.1f} | {'':<40}"
            )
    print(separator)

    # ---------------------------------------------------------
    # PHASE 4: CLEANUP (Delete all created indices)
    # ---------------------------------------------------------
    print("\n" + "=" * 60)
    print(" CLEANING UP INDICES")
    print("=" * 60)

    all_indices = set(dataset_to_index_map.values())
    # Also include indices from failed datasets (they might have been created before failing)
    for failure_info in failed_datasets.values():
        if "index_name" in failure_info:
            all_indices.add(failure_info["index_name"])

    if all_indices:
        print(f"\n🗑️  Deleting {len(all_indices)} indices...")
        for index_name in sorted(all_indices):
            try:
                await client.delete_index(index_name)
                print(f"   ✅ Deleted: {index_name}")
            except Exception as e:
                print(f"   ⚠️  Failed to delete {index_name}: {e}")
    else:
        print("\n   No indices to delete.")

    print("\nDone.")


@pytest.mark.asyncio
async def test_search_benchmark():
    """Run the Multi-Dataset benchmark as a pytest test."""
    await main()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
