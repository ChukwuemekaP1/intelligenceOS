"""Deterministic retrieval and citation metrics for evaluation."""

import math
import uuid


def compute_recall_at_k(
    retrieved_chunk_ids: list[uuid.UUID | str],
    expected_chunk_ids: list[uuid.UUID | str],
    k: int = 5,
) -> float:
    """Computes Recall@K: fraction of expected relevant chunks present in top-K retrieved.

    Recall@K = |Retrieved@K ∩ Expected| / |Expected|
    """
    if not expected_chunk_ids:
        return 1.0  # Perfect recall if no chunks were strictly required

    top_k_retrieved = {str(cid) for cid in retrieved_chunk_ids[:k]}
    expected_set = {str(cid) for cid in expected_chunk_ids}

    matched = len(top_k_retrieved.intersection(expected_set))
    return round(float(matched) / float(len(expected_set)), 4)


def compute_mrr(
    retrieved_chunk_ids: list[uuid.UUID | str],
    expected_chunk_ids: list[uuid.UUID | str],
) -> float:
    """Computes Mean Reciprocal Rank (MRR): 1 / rank of the first relevant chunk found."""
    if not expected_chunk_ids or not retrieved_chunk_ids:
        return 0.0

    expected_set = {str(cid) for cid in expected_chunk_ids}
    for rank, cid in enumerate(retrieved_chunk_ids, start=1):
        if str(cid) in expected_set:
            return round(1.0 / float(rank), 4)

    return 0.0


def compute_ndcg_at_k(
    retrieved_chunk_ids: list[uuid.UUID | str],
    relevance_scores: dict[str, float] | list[uuid.UUID | str],
    k: int = 5,
) -> float:
    """Computes normalized Discounted Cumulative Gain (nDCG@K).

    relevance_scores can be:
    - dict[chunk_id_str, gain_value]
    - list of relevant chunk_ids (where relevance = 1.0)
    """
    if isinstance(relevance_scores, list):
        gain_dict = {str(cid): 1.0 for cid in relevance_scores}
    else:
        gain_dict = {str(k_id): float(v) for k_id, v in relevance_scores.items()}

    if not gain_dict:
        return 1.0

    # DCG@K
    dcg = 0.0
    for rank, cid in enumerate(retrieved_chunk_ids[:k], start=1):
        rel = gain_dict.get(str(cid), 0.0)
        if rel > 0:
            dcg += (2.0**rel - 1.0) / math.log2(rank + 1)

    # Ideal DCG (IDCG@K)
    sorted_ideal = sorted(gain_dict.values(), reverse=True)[:k]
    idcg = 0.0
    for rank, rel in enumerate(sorted_ideal, start=1):
        if rel > 0:
            idcg += (2.0**rel - 1.0) / math.log2(rank + 1)

    if idcg == 0.0:
        return 0.0

    return round(dcg / idcg, 4)


def evaluate_citations(
    generated_citation_ids: list[uuid.UUID | str],
    expected_citation_ids: list[uuid.UUID | str],
) -> dict[str, float]:
    """Computes deterministic precision, recall, and F1 for citation correctness."""
    gen_set = {str(cid) for cid in generated_citation_ids}
    exp_set = {str(cid) for cid in expected_citation_ids}

    if not exp_set and not gen_set:
        return {"precision": 1.0, "recall": 1.0, "f1": 1.0}
    if not gen_set:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0}
    if not exp_set:
        return {"precision": 0.0, "recall": 1.0, "f1": 0.0}

    tp = len(gen_set.intersection(exp_set))
    precision = float(tp) / float(len(gen_set))
    recall = float(tp) / float(len(exp_set))
    f1 = (2.0 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
    }
