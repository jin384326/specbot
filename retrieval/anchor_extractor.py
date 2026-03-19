from __future__ import annotations

from parser.models import DocRecord
from retrieval.anchor_normalizer import is_noisy_anchor, normalize_anchor


def extract_anchor_candidates(records: list[DocRecord]) -> list[dict]:
    candidates: dict[str, dict] = {}
    for record in records:
        source_terms = [
            *record.ie_names,
            *record.message_names,
            *record.procedure_names,
            *record.table_headers,
            record.row_header,
            *record.referenced_specs,
            *record.acronyms,
            *record.camel_case_identifiers,
            record.clause_title,
        ]
        for term in source_terms:
            normalized = normalize_anchor(term)
            if is_noisy_anchor(normalized):
                continue
            payload = candidates.setdefault(
                normalized.lower(),
                {"anchor": normalized, "sources": set(), "doc_ids": set(), "spec_nos": set()},
            )
            payload["doc_ids"].add(record.doc_id)
            if record.spec_no:
                payload["spec_nos"].add(record.spec_no)
            if term in record.ie_names:
                payload["sources"].add("ie_name")
            if term in record.message_names:
                payload["sources"].add("message_name")
            if term in record.procedure_names:
                payload["sources"].add("procedure_name")
            if term in record.table_headers or term == record.row_header:
                payload["sources"].add("table")
            if term in record.referenced_specs:
                payload["sources"].add("spec_reference")
            if term in record.acronyms:
                payload["sources"].add("acronym")
            if term in record.camel_case_identifiers:
                payload["sources"].add("camel_case")
            if term == record.clause_title:
                payload["sources"].add("clause_title")
    return [
        {
            "anchor": item["anchor"],
            "sources": sorted(item["sources"]),
            "doc_count": len(item["doc_ids"]),
            "spec_count": len(item["spec_nos"]),
        }
        for item in candidates.values()
    ]
