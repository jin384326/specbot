from __future__ import annotations

import re

SOURCE_WEIGHTS = {
    "ie_name": 2.5,
    "message_name": 2.5,
    "procedure_name": 1.8,
    "table": 1.5,
    "spec_reference": 1.4,
    "acronym": 1.0,
    "camel_case": 1.0,
    "clause_title": 1.2,
}
GENERIC_ANCHOR_TERMS = {
    "note",
    "ts",
    "ran",
    "path",
    "paths",
    "end",
    "message",
    "messages",
    "procedure",
    "procedures",
}


def anchor_penalty(anchor: str, sources: list[str]) -> float:
    normalized = anchor.strip()
    lowered = normalized.lower()
    penalty = 0.0
    if lowered in GENERIC_ANCHOR_TERMS:
        penalty += 3.0
    if normalized.isdigit():
        penalty += 2.4
    if len(normalized.split()) >= 8:
        penalty += 2.2
    if "procedure_name" in sources and len(normalized.split()) >= 6:
        penalty += 1.6
    if "acronym" in sources and len(normalized) <= 4:
        penalty += 1.8
    if re.search(r"\bthis request\b", lowered):
        penalty += 2.5
    return penalty


def select_anchors(candidates: list[dict], limit: int = 8) -> list[dict]:
    ranked = []
    for item in candidates:
        sources = item.get("sources", [])
        score = sum(SOURCE_WEIGHTS.get(source, 0.0) for source in sources)
        score += 0.2 * item.get("doc_count", 0)
        score += 0.4 * max(0, item.get("spec_count", 0) - 1)
        score += 0.8 * item.get("query_overlap", 0)
        score -= anchor_penalty(item.get("anchor", ""), sources)
        if score <= 0:
            continue
        ranked.append({**item, "score": round(score, 3)})
    return sorted(ranked, key=lambda item: (-item["score"], item["anchor"].lower()))[:limit]
