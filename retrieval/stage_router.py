from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field

from parser.models import DocRecord
from retrieval.query_normalizer import NormalizedQuery, expand_compound_variants, iter_registry_terms

STAGE_BUCKET_ORDER = ["Stage 2", "Stage 3", "else"]
MAX_TERMS_PER_SPEC = 48


@dataclass
class RoutingIndex:
    spec_stage_index: dict[str, list[str]] = field(default_factory=dict)
    stage_representatives: dict[str, list[str]] = field(default_factory=dict)
    spec_term_scores: dict[str, dict[str, float]] = field(default_factory=dict)
    spec_titles: dict[str, str] = field(default_factory=dict)
    spec_clause_titles: dict[str, list[str]] = field(default_factory=dict)


def dedupe_preserve_order(values: list[str]) -> list[str]:
    deduped: list[str] = []
    for value in values:
        candidate = value.strip()
        if candidate and candidate not in deduped:
            deduped.append(candidate)
    return deduped


def resolve_stage_buckets(normalized: NormalizedQuery) -> list[str]:
    if normalized.stage_filters:
        return dedupe_preserve_order(normalized.stage_filters)
    return list(STAGE_BUCKET_ORDER)


def build_routing_index(records: list[DocRecord]) -> RoutingIndex:
    spec_stage_map: dict[str, set[str]] = defaultdict(set)
    stage_spec_counts: dict[str, Counter[str]] = defaultdict(Counter)
    spec_term_scores: dict[str, Counter[str]] = defaultdict(Counter)
    spec_titles: dict[str, str] = {}
    spec_clause_title_counts: dict[str, Counter[str]] = defaultdict(Counter)

    for record in records:
        if not record.spec_no:
            continue
        if record.spec_title and record.spec_no not in spec_titles:
            spec_titles[record.spec_no] = record.spec_title
        if record.stage_hint:
            spec_stage_map[record.spec_no].add(record.stage_hint)
            stage_spec_counts[record.stage_hint][record.spec_no] += 1
        if record.clause_title:
            spec_clause_title_counts[record.spec_no][record.clause_title] += 1

        weighted_terms = list(iter_registry_terms(record))
        for normalized in expand_compound_variants(record.spec_title):
            weighted_terms.append((normalized, 2.4))
        if record.entity_name:
            for normalized in expand_compound_variants(record.entity_name):
                weighted_terms.append((normalized, 2.2))

        for term, weight in weighted_terms:
            if not term or len(term) < 4:
                continue
            spec_term_scores[record.spec_no][term] += weight

    ordered_stage_index = {
        spec_no: [stage for stage in STAGE_BUCKET_ORDER if stage in stage_hints]
        for spec_no, stage_hints in spec_stage_map.items()
    }
    stage_representatives = {
        stage: [spec_no for spec_no, _ in sorted(counter.items(), key=lambda item: (-item[1], item[0]))]
        for stage, counter in stage_spec_counts.items()
    }
    ranked_term_scores = {
        spec_no: {
            term: round(score, 3)
            for term, score in sorted(term_counter.items(), key=lambda item: (-item[1], item[0]))[:MAX_TERMS_PER_SPEC]
        }
        for spec_no, term_counter in spec_term_scores.items()
    }
    ranked_clause_titles = {
        spec_no: [title for title, _ in sorted(counter.items(), key=lambda item: (-item[1], item[0]))[:MAX_TERMS_PER_SPEC]]
        for spec_no, counter in spec_clause_title_counts.items()
    }
    return RoutingIndex(
        spec_stage_index=ordered_stage_index,
        stage_representatives=stage_representatives,
        spec_term_scores=ranked_term_scores,
        spec_titles=spec_titles,
        spec_clause_titles=ranked_clause_titles,
    )


def resolve_spec_stage_filters(spec_no: str, requested_buckets: list[str], routing_index: RoutingIndex) -> list[str]:
    observed_buckets = routing_index.spec_stage_index.get(spec_no, [])
    if not observed_buckets:
        return list(requested_buckets)
    matched_buckets = [bucket for bucket in requested_buckets if bucket in observed_buckets]
    return matched_buckets or list(observed_buckets)


def infer_primary_stage_specs(stage_buckets: list[str], routing_index: RoutingIndex, limit: int = 1) -> list[str]:
    selected: list[str] = []
    for stage_bucket in stage_buckets:
        for spec_no in routing_index.stage_representatives.get(stage_bucket, [])[:limit]:
            if spec_no not in selected:
                selected.append(spec_no)
        if selected:
            break
    return selected


def infer_entry_specs(
    normalized: NormalizedQuery,
    routing_index: RoutingIndex,
    *,
    stage_buckets: list[str] | None = None,
    limit: int = 6,
) -> list[str]:
    requested_buckets = stage_buckets or resolve_stage_buckets(normalized)
    query_terms = dedupe_preserve_order(
        [
            *normalized.hinted_specs,
            *normalized.inferred_specs,
            normalized.normalized_query,
            *normalized.candidate_anchors,
            *normalized.aliases,
            *normalized.features.get("tokens", []),
        ]
    )
    query_terms_lower = [term.lower() for term in query_terms if term]
    query_phrase = normalized.normalized_query.lower()
    anchor_phrases = [candidate.lower() for candidate in normalized.candidate_anchors[:8]]

    scored_specs: list[tuple[str, float]] = []
    for spec_no, terms in routing_index.spec_term_scores.items():
        score = 0.0
        for query_term in query_terms_lower:
            for indexed_term, weight in terms.items():
                indexed_term_lower = indexed_term.lower()
                if query_term == indexed_term_lower:
                    score += weight
                elif len(query_term) >= 5 and (query_term in indexed_term_lower or indexed_term_lower in query_term):
                    score += weight * 0.55
        spec_title_lower = routing_index.spec_titles.get(spec_no, "").lower()
        if query_phrase and spec_title_lower:
            if query_phrase == spec_title_lower:
                score += 8.0
            elif len(query_phrase) >= 5 and query_phrase in spec_title_lower:
                score += 4.2
        for clause_title in routing_index.spec_clause_titles.get(spec_no, [])[:16]:
            clause_title_lower = clause_title.lower()
            if not clause_title_lower:
                continue
            if query_phrase and query_phrase == clause_title_lower:
                score += 9.5
            elif query_phrase and len(query_phrase) >= 5 and query_phrase in clause_title_lower:
                score += 5.0
            for anchor_phrase in anchor_phrases:
                if len(anchor_phrase) >= 5 and anchor_phrase in clause_title_lower:
                    score += 2.6
        if score <= 0:
            continue
        observed_buckets = routing_index.spec_stage_index.get(spec_no, [])
        if observed_buckets and any(bucket in observed_buckets for bucket in requested_buckets):
            score += 1.5
        scored_specs.append((spec_no, round(score, 3)))

    seeds = dedupe_preserve_order(
        [
            *normalized.hinted_specs,
            *infer_primary_stage_specs(requested_buckets, routing_index, limit=1),
            *[spec_no for spec_no, _ in sorted(scored_specs, key=lambda item: (-item[1], item[0]))[: max(limit, 3)]],
        ]
    )
    if seeds:
        return seeds[:limit]

    fallback_specs: list[str] = []
    for stage_bucket in requested_buckets:
        fallback_specs.extend(routing_index.stage_representatives.get(stage_bucket, [])[:2])
    return dedupe_preserve_order(fallback_specs)[:limit]


def build_spec_candidates(
    normalized: NormalizedQuery,
    routing_index: RoutingIndex,
    *,
    stage_buckets: list[str] | None = None,
    limit: int = 8,
) -> list[dict[str, object]]:
    requested_buckets = stage_buckets or resolve_stage_buckets(normalized)
    ranked_specs = infer_entry_specs(normalized, routing_index, stage_buckets=requested_buckets, limit=limit)
    candidates: list[dict[str, object]] = []
    for spec_no in ranked_specs:
        candidates.append(
            {
                "spec_id": spec_no,
                "spec_no": spec_no,
                "spec_title": routing_index.spec_titles.get(spec_no, ""),
                "stage_hints": routing_index.spec_stage_index.get(spec_no, []),
                "top_terms": list(routing_index.spec_term_scores.get(spec_no, {}).keys())[:8],
                "top_clause_titles": routing_index.spec_clause_titles.get(spec_no, [])[:5],
            }
        )
    return candidates[:limit]
