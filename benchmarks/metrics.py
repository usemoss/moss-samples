"""Recall, nDCG, R-precision and latency metrics, matching VectorDBBench, BEIR and ann-benchmarks conventions (see README.md)."""

import math
from collections.abc import Sequence

import numpy as np


def recall(got: Sequence[Sequence[int]], gt: np.ndarray, k: int) -> float:
    """VectorDBBench calc_recall: |got[:k] ∩ gt[:k]| / k, averaged over queries."""
    return float(
        np.mean([len(set(g[:k]) & set(t[:k].tolist())) / k for g, t in zip(got, gt)])
    )


def ndcg_gt(got: Sequence[Sequence[int]], gt: np.ndarray, k: int) -> float:
    """VectorDBBench calc_vector_metrics nDCG: each unique hit adds 1/log2(gt_rank + 2), over the ideal DCG."""
    ideal = sum(1 / math.log2(i + 2) for i in range(k))
    scores = []
    for g, t in zip(got, gt):
        rank: dict[int, int] = {}
        for i, d in enumerate(t[:k].tolist()):
            rank.setdefault(d, i)
        scores.append(
            sum(1 / math.log2(rank[d] + 2) for d in set(g[:k]) if d in rank) / ideal
        )
    return float(np.mean(scores))


def ndcg_qrels(
    got: dict[str, list[str]], qrels: dict[str, dict[str, int]], k: int = 10
) -> float:
    """trec_eval ndcg_cut (linear gain): sum rel_i / log2(i + 1) over ranks 1..k, divided by the ideal ordering."""
    scores = []
    for q, rels in qrels.items():
        dcg = sum(
            rels.get(d, 0) / math.log2(i + 2) for i, d in enumerate(got.get(q, [])[:k])
        )
        ideal = sum(
            r / math.log2(i + 2)
            for i, r in enumerate(sorted(rels.values(), reverse=True)[:k])
        )
        scores.append(dcg / ideal if ideal else 0.0)
    return float(np.mean(scores))


def recall_qrels(
    got: dict[str, list[str]], qrels: dict[str, dict[str, int]], k: int = 100
) -> float:
    """BEIR recall@k: relevant docs retrieved in the top k, over all relevant docs, averaged over queries."""
    return float(
        np.mean(
            [len(set(got.get(q, [])[:k]) & set(r)) / len(r) for q, r in qrels.items()]
        )
    )


def r_precision(got: dict[str, list[str]], qrels: dict[str, dict[str, int]]) -> float:
    """trec_eval Rprec: relevant docs (grade > 0) in the top R over R, R = the query's relevant-doc count."""
    scores = []
    for q, rels in qrels.items():
        rel = {d for d, g in rels.items() if g > 0}
        scores.append(
            len(set(got.get(q, [])[: len(rel)]) & rel) / len(rel) if rel else 0.0
        )
    return float(np.mean(scores))


def latency_summary(seconds: Sequence[float]) -> dict[str, float]:
    """Count, mean and p50/p95/p99/p99.9 in milliseconds (numpy linear-interpolated percentiles)."""
    ms = np.asarray(seconds) * 1000
    p50, p95, p99, p999 = np.percentile(ms, [50, 95, 99, 99.9])
    return {
        "n": len(ms),
        "mean": float(ms.mean()),
        "p50": float(p50),
        "p95": float(p95),
        "p99": float(p99),
        "p999": float(p999),
    }
