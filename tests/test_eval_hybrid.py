from __future__ import annotations

from tools.eval_hybrid import ndcg_at_k_doc, parse_sweep, reciprocal_rank_doc


def test_parse_sweep_accepts_profile_sparse_and_vector_boost() -> None:
    assert parse_sweep(["hybrid:1.0:0.8", "bm25:1.0:0.0"]) == [
        ("hybrid", 1.0, 0.8),
        ("bm25", 1.0, 0.0),
    ]


def test_doc_metrics_are_computed_from_hits() -> None:
    hits = [
        {"fields": {"doc_id": "a"}},
        {"fields": {"doc_id": "b"}},
        {"fields": {"doc_id": "c"}},
    ]
    assert reciprocal_rank_doc(hits, {"b"}) == 0.5
    assert ndcg_at_k_doc(hits, {"a", "c"}, 3) > 0.9
