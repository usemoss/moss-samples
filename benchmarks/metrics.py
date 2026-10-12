"""Recall, nDCG, R-precision and latency metrics.

The definitions match VectorDBBench, BEIR (trec_eval) and ann-benchmarks conventions (see
README.md).
"""

import math
from collections.abc import Sequence

import numpy as np


def recall(got: Sequence[Sequence[int]], gt: np.ndarray, k: int) -> float:
    """Mean recall@k against exact ground truth (VectorDBBench calc_recall).

    Per query, |got[:k] ∩ gt[:k]| / k, averaged over the queries.

    Args:
        got: Returned doc ids per query, best first; a list may be shorter than k.
        gt: Exact neighbor ids per query, shape (n_queries, >= k), best first; -1 pads rows with
            fewer neighbors and never matches a doc.
        k: Cutoff for both the returned ids and the ground truth.

    Returns:
        Recall@k averaged over the queries, in [0, 1].
    """
    return float(np.mean([len(set(g[:k]) & set(t[:k].tolist())) / k for g, t in zip(got, gt)]))


def ndcg_gt(got: Sequence[Sequence[int]], gt: np.ndarray, k: int) -> float:
    """Mean nDCG@k graded by rank in the exact ground truth (VectorDBBench calc_vector_metrics).

    Each unique returned id found in gt[:k] adds 1 / log2(gt_rank + 2), where gt_rank is its 0-based
    position in the ground truth; the sum is divided by the ideal DCG of k hits. The order of the
    returned ids does not change the score.

    Args:
        got: Returned doc ids per query.
        gt: Exact neighbor ids per query, shape (n_queries, >= k), best first.
        k: Cutoff for both the returned ids and the ground truth.

    Returns:
        nDCG@k averaged over the queries, in [0, 1].
    """
    ideal = sum(1 / math.log2(i + 2) for i in range(k))
    scores = []
    for g, t in zip(got, gt):
        rank: dict[int, int] = {}
        for i, d in enumerate(t[:k].tolist()):
            rank.setdefault(d, i)
        scores.append(sum(1 / math.log2(rank[d] + 2) for d in set(g[:k]) if d in rank) / ideal)
    return float(np.mean(scores))


def ndcg_qrels(got: dict[str, list[str]], qrels: dict[str, dict[str, int]], k: int = 10) -> float:
    """Mean nDCG@k against human relevance labels (trec_eval ndcg_cut, linear gain).

    DCG sums rel_i / log2(i + 1) over result ranks i = 1..k, where rel_i is the result's grade (0 if
    unlabelled); it is divided by the DCG of the query's grades in descending order. A query with no
    results, or with an ideal DCG of 0, scores 0.

    Args:
        got: Returned doc ids (as strings) per query id, best first.
        qrels: Relevance grade per doc id, per query id; every query in qrels is scored.
        k: Rank cutoff.

    Returns:
        nDCG@k averaged over the queries in qrels.
    """
    scores = []
    for q, rels in qrels.items():
        dcg = sum(rels.get(d, 0) / math.log2(i + 2) for i, d in enumerate(got.get(q, [])[:k]))
        ideal = sum(
            r / math.log2(i + 2) for i, r in enumerate(sorted(rels.values(), reverse=True)[:k])
        )
        scores.append(dcg / ideal if ideal else 0.0)
    return float(np.mean(scores))


def recall_qrels(
    got: dict[str, list[str]], qrels: dict[str, dict[str, int]], k: int = 100
) -> float:
    """Mean recall@k against human relevance labels (BEIR).

    Per query, the labelled docs found in the top k over all docs labelled for that query.

    Args:
        got: Returned doc ids (as strings) per query id, best first.
        qrels: Relevance grade per doc id, per query id; every query in qrels is scored, and every
            doc listed for a query counts as relevant.
        k: Rank cutoff.

    Returns:
        Recall@k averaged over the queries in qrels.
    """
    return float(
        np.mean([len(set(got.get(q, [])[:k]) & set(r)) / len(r) for q, r in qrels.items()])
    )


def r_precision(got: dict[str, list[str]], qrels: dict[str, dict[str, int]]) -> float:
    """Mean R-precision against human relevance labels (trec_eval Rprec).

    Per query, R is its number of relevant docs (grade > 0) and the score is the share of its top R
    results that are relevant. A query with no relevant docs scores 0.

    Args:
        got: Returned doc ids (as strings) per query id, best first.
        qrels: Relevance grade per doc id, per query id; every query in qrels is scored.

    Returns:
        R-precision averaged over the queries in qrels.
    """
    scores = []
    for q, rels in qrels.items():
        rel = {d for d, g in rels.items() if g > 0}
        scores.append(len(set(got.get(q, [])[: len(rel)]) & rel) / len(rel) if rel else 0.0)
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
