from __future__ import annotations

from retrieval.relevance_signals import RelevanceSignals


DEFAULT_SIGNAL_WEIGHTS = {
    "clause_title_exact_match": 4.8,
    "clause_title_match": 1.8,
    "ie_name_match": 2.2,
    "message_name_match": 2.2,
    "procedure_name_match": 1.8,
    "table_header_match": 1.5,
    "table_row_match": 1.2,
    "explicit_spec_reference": 1.0,
    "semantic_similarity": 1.4,
}


def score_relevance(signals: RelevanceSignals, weights: dict[str, float] | None = None) -> tuple[float, dict[str, float]]:
    active_weights = {**DEFAULT_SIGNAL_WEIGHTS, **(weights or {})}
    breakdown = {
        key: round(value * active_weights.get(key, 0.0), 3)
        for key, value in signals.to_dict().items()
        if value > 0
    }
    return round(sum(breakdown.values()), 3), breakdown
