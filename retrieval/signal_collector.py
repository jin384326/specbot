from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from parser.models import DocRecord

GENERIC_SIGNALS = {"general", "overview", "introduction", "procedure", "procedures", "network", "service"}


def classify_signal(score: float) -> str:
    if score >= 4.0:
        return "strong"
    if score >= 1.5:
        return "normal"
    return "reject"


def collect_expansion_signals(seed_docs: Iterable[DocRecord]) -> list[dict]:
    scores: dict[str, float] = defaultdict(float)
    reasons: dict[str, set[str]] = defaultdict(set)
    for record in seed_docs:
        for anchor in record.anchor_terms:
            if anchor:
                scores[anchor] += 2.0
                reasons[anchor].add("strong_anchor")
        for spec in record.referenced_specs:
            scores[spec] += 1.5
            reasons[spec].add("referenced_spec")
        for clause in record.referenced_clauses:
            scores[clause] += 1.0
            reasons[clause].add("referenced_clause")
        if record.row_header:
            scores[record.row_header] += 1.1
            reasons[record.row_header].add("row_header")
        for term in record.keywords[:5]:
            scores[term] += 0.6
            reasons[term].add("keyword")
    return sorted(
        (
            {
                "signal": signal,
                "score": round(score - (1.5 if signal.lower() in GENERIC_SIGNALS else 0.0), 3),
                "reasons": sorted(reasons[signal]),
                "classification": classify_signal(score - (1.5 if signal.lower() in GENERIC_SIGNALS else 0.0)),
            }
            for signal, score in scores.items()
            if signal.strip()
        ),
        key=lambda item: (-item["score"], item["signal"]),
    )
