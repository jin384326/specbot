from __future__ import annotations

from dataclasses import dataclass

from parser.models import DocRecord
from retrieval.query_normalizer import NormalizedQuery


@dataclass
class RelevanceSignals:
    clause_title_exact_match: float = 0.0
    clause_title_match: float = 0.0
    ie_name_match: float = 0.0
    message_name_match: float = 0.0
    procedure_name_match: float = 0.0
    table_header_match: float = 0.0
    table_row_match: float = 0.0
    explicit_spec_reference: float = 0.0
    semantic_similarity: float = 0.0

    def to_dict(self) -> dict[str, float]:
        return {
            "clause_title_exact_match": self.clause_title_exact_match,
            "clause_title_match": self.clause_title_match,
            "ie_name_match": self.ie_name_match,
            "message_name_match": self.message_name_match,
            "procedure_name_match": self.procedure_name_match,
            "table_header_match": self.table_header_match,
            "table_row_match": self.table_row_match,
            "explicit_spec_reference": self.explicit_spec_reference,
            "semantic_similarity": self.semantic_similarity,
        }


def _contains_any(needles: list[str], haystacks: list[str]) -> float:
    lowered_haystacks = [item.lower() for item in haystacks if item]
    if not lowered_haystacks:
        return 0.0
    matched = 0
    for needle in needles:
        candidate = needle.strip().lower()
        if candidate and any(candidate in haystack for haystack in lowered_haystacks):
            matched += 1
    return float(matched)


def _exact_or_phrase_match(needles: list[str], haystack: str) -> float:
    lowered_haystack = haystack.strip().lower()
    if not lowered_haystack:
        return 0.0
    best = 0.0
    for needle in needles:
        candidate = needle.strip().lower()
        if not candidate:
            continue
        if candidate == lowered_haystack:
            best = max(best, 2.0)
        elif len(candidate) >= 5 and candidate in lowered_haystack:
            best = max(best, 1.0)
    return best


def collect_relevance_signals(query: NormalizedQuery, record: DocRecord, retrieval_score: float = 0.0) -> RelevanceSignals:
    anchors = query.candidate_anchors + query.aliases + query.features.get("tokens", [])
    return RelevanceSignals(
        clause_title_exact_match=_exact_or_phrase_match(anchors, record.clause_title),
        clause_title_match=_contains_any(anchors, [record.clause_title]),
        ie_name_match=_contains_any(query.candidate_anchors + query.aliases, record.ie_names),
        message_name_match=_contains_any(query.candidate_anchors + query.aliases, record.message_names),
        procedure_name_match=_contains_any(query.candidate_anchors + query.aliases, record.procedure_names),
        table_header_match=_contains_any(query.candidate_anchors + query.aliases, [*record.table_headers, record.row_header]),
        table_row_match=_contains_any(query.candidate_anchors + query.aliases, record.row_cells),
        explicit_spec_reference=1.0 if set(query.hinted_specs + query.inferred_specs).intersection(record.referenced_specs) else 0.0,
        semantic_similarity=max(retrieval_score, 0.0),
    )
