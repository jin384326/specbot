from __future__ import annotations

from typing import Iterable


def merge_clause_results(hit_groups: Iterable[dict]) -> list[dict]:
    merged: dict[str, dict] = {}
    for item in hit_groups:
        doc = item["doc"]
        clause_key = f"{doc.spec_no}:{doc.clause_id or doc.doc_id}"
        payload = merged.setdefault(
            clause_key,
            {
                "clause_key": clause_key,
                "spec_no": doc.spec_no,
                "clause_id": doc.clause_id,
                "clause_title": doc.clause_title,
                "score": 0.0,
                "doc_ids": [],
                "reason_types": set(),
                "docs": [],
            },
        )
        payload["score"] = max(payload["score"], float(item.get("score", 0.0)))
        payload["doc_ids"].append(doc.doc_id)
        payload["reason_types"].add(item.get("reason_type", "unknown"))
        payload["docs"].append(doc)
    ranked = []
    for payload in merged.values():
        ranked.append(
            {
                **payload,
                "doc_ids": sorted(set(payload["doc_ids"])),
                "reason_types": sorted(payload["reason_types"]),
            }
        )
    return sorted(ranked, key=lambda item: (-item["score"], item["clause_key"]))
