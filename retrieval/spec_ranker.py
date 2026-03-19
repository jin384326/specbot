from __future__ import annotations

from collections import defaultdict
from math import log1p
from typing import Iterable


DEFAULT_WEIGHTS = {
    "direct_hit": 3.0,
    "anchor_hit": 2.0,
    "table_row_hit": 1.8,
    "referenced_spec_hit": 1.2,
}


def rank_specs(hit_groups: Iterable[dict], weights: dict[str, float] | None = None) -> list[dict]:
    active_weights = {**DEFAULT_WEIGHTS, **(weights or {})}
    by_spec: dict[str, dict] = defaultdict(
        lambda: {"weighted_scores": [], "reasons": [], "doc_ids": set(), "reason_types": set()}
    )

    for hit in hit_groups:
        spec_no = hit.get("spec_no") or "unknown"
        reason_type = hit.get("reason_type", "direct_hit")
        weight = active_weights.get(reason_type, 1.0)
        score = float(hit.get("score", 1.0)) * weight
        payload = by_spec[spec_no]
        payload["weighted_scores"].append(score)
        payload["doc_ids"].add(hit.get("doc_id", ""))
        payload["reason_types"].add(reason_type)
        explanation = hit.get("explanation") or hit.get("matched_text") or reason_type
        payload["reasons"].append(f"{reason_type}: {explanation}")

    ranked = []
    for spec_no, payload in by_spec.items():
        sorted_scores = sorted(payload["weighted_scores"], reverse=True)
        blended_score = sum(score / (index + 1) ** 0.8 for index, score in enumerate(sorted_scores[:5]))
        blended_score += 0.35 * log1p(len(payload["doc_ids"]))
        blended_score += 0.45 * max(0, len(payload["reason_types"]) - 1)
        ranked.append(
            {
                "spec_no": spec_no,
                "score": round(blended_score, 3),
                "doc_count": len([doc_id for doc_id in payload["doc_ids"] if doc_id]),
                "explanation": "; ".join(payload["reasons"][:5]),
            }
        )
    return sorted(ranked, key=lambda item: (-item["score"], item["spec_no"]))
