from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from retrieval.query_normalizer import NormalizedQuery


@dataclass
class VespaQueryRequest:
    yql: str
    ranking: str = "bm25"
    hits: int = 10
    query_profile: str = "default"
    additional_params: dict[str, str] = field(default_factory=dict)

    def to_params(self) -> dict[str, str | int]:
        return {
            "yql": self.yql,
            "ranking": self.ranking,
            "hits": self.hits,
            "queryProfile": self.query_profile,
            **self.additional_params,
        }


def build_contains_expression(field: str, terms: list[str]) -> str:
    unique_terms: list[str] = []
    for term in terms:
        candidate = term.strip()
        if not candidate or candidate in unique_terms:
            continue
        unique_terms.append(candidate)
    expressions = [f'{field} contains "{term}"' for term in unique_terms]
    return " or ".join(expressions) if expressions else "false"


def build_tensor_literal(values: list[float]) -> str:
    serialized = ", ".join(f"{value:.6f}" for value in values)
    return f"tensor<float>(x[{len(values)}]):[{serialized}]"


def expand_spec_hint_terms(spec_terms: list[str]) -> list[str]:
    expanded: list[str] = []
    for spec in spec_terms:
        candidate = spec.strip()
        if not candidate:
            continue
        variants = [candidate]
        if len(candidate) == 5 and candidate.isdigit():
            variants.extend([f"{candidate[:2]}.{candidate[2:]}", f"TS {candidate[:2]}.{candidate[2:]}"])
        for variant in variants:
            if variant not in expanded:
                expanded.append(variant)
    return expanded


def build_vespa_query(
    normalized_query: NormalizedQuery,
    hits: int = 10,
    release_filters: list[str] | None = None,
    release_data_filters: list[str] | None = None,
) -> VespaQueryRequest:
    text_terms = normalized_query.features.get("tokens", [])[:6]
    phrase_terms = [term for term in normalized_query.candidate_anchors if len(term.split()) >= 4][:2]
    if not phrase_terms and len(normalized_query.normalized_query.split()) >= 4:
        phrase_terms = [normalized_query.normalized_query]
    spec_terms = normalized_query.hinted_specs
    inferred_spec_terms = normalized_query.inferred_specs
    stage_terms = normalized_query.hinted_stages
    stage_filters = normalized_query.stage_filters
    soft_spec_terms = spec_terms or inferred_spec_terms
    spec_hint_terms = expand_spec_hint_terms(soft_spec_terms)
    text_filter = build_contains_expression("text", text_terms)
    phrase_filter = " or ".join(
        clause
        for clause in [
            build_contains_expression("clause_title", phrase_terms),
            build_contains_expression("table_title", phrase_terms),
            build_contains_expression("row_header", phrase_terms),
            build_contains_expression("entity_name", phrase_terms),
            build_contains_expression("embedding_text", phrase_terms),
            build_contains_expression("text", phrase_terms),
        ]
        if clause != "false"
    )
    alias_text_filter = " or ".join(
        clause
        for clause in [
            build_contains_expression("text", normalized_query.aliases[:6]),
            build_contains_expression("embedding_text", normalized_query.aliases[:6]),
        ]
        if clause != "false"
    )
    title_filter = " or ".join(
        clause
        for clause in [
            build_contains_expression("clause_title", normalized_query.candidate_anchors[:6]),
            build_contains_expression("table_title", normalized_query.candidate_anchors[:6]),
            build_contains_expression("row_header", normalized_query.candidate_anchors[:6]),
            build_contains_expression("entity_name", normalized_query.candidate_anchors[:6]),
        ]
        if clause != "false"
    )
    anchor_filter = " or ".join(
        clause
        for clause in [
            build_contains_expression("anchor_terms", normalized_query.aliases + normalized_query.candidate_anchors[:6]),
            build_contains_expression("ie_names", normalized_query.aliases + normalized_query.candidate_anchors[:6]),
            build_contains_expression("message_names", normalized_query.aliases + normalized_query.candidate_anchors[:6]),
            build_contains_expression("procedure_names", normalized_query.aliases + normalized_query.candidate_anchors[:6]),
        ]
        if clause != "false"
    )
    spec_hint_clause = " or ".join(
        clause
        for clause in [
            build_contains_expression("spec_no", soft_spec_terms),
            build_contains_expression("embedding_text", spec_hint_terms),
            build_contains_expression("text", spec_hint_terms),
        ]
        if clause != "false"
    )
    stage_hint_clause = build_contains_expression("stage_hint", stage_terms)
    content_clause_parts = [
        clause
        for clause in [phrase_filter, text_filter, alias_text_filter, title_filter, anchor_filter, spec_hint_clause, stage_hint_clause]
        if clause and clause != "false"
    ]
    where_clause = "(" + " or ".join(content_clause_parts or ["userQuery()"]) + ")"
    if spec_terms:
        where_clause = where_clause + " and (" + build_contains_expression("spec_no", spec_terms) + ")"
    if stage_filters:
        where_clause = where_clause + " and (" + build_contains_expression("stage_hint", stage_filters) + ")"
    if release_filters:
        where_clause = where_clause + " and (" + build_contains_expression("release", release_filters) + ")"
    if release_data_filters:
        where_clause = where_clause + " and (" + build_contains_expression("release_data", release_data_filters) + ")"

    additional_params: dict[str, Any] = {"query": normalized_query.normalized_query}
    if normalized_query.query_vector:
        additional_params["input.query(query_embedding)"] = build_tensor_literal(normalized_query.query_vector)
        yql = (
            "select * from sources * where "
            + "rank("
            + where_clause
            + f", {{targetHits:{max(hits * 5, 50)}}}nearestNeighbor(dense_embedding, query_embedding))"
        )
    else:
        yql = "select * from sources * where " + where_clause
    return VespaQueryRequest(yql=yql, hits=hits, additional_params=additional_params)
