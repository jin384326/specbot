from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from parser.models import doc_record_from_dict

ALIAS_PATTERN = re.compile(r"\b([A-Z][A-Z0-9\-]{1,})\b")
SPEC_PATTERN = re.compile(r"\b(?:3GPP\s+)?(?:TS|TR)?\s*(\d{2}\.\d{3}|\d{5})\b")
STAGE_PATTERN = re.compile(r"\b(stage\s+\d+)\b", re.IGNORECASE)
ELSE_STAGE_PATTERN = re.compile(r"\belse\b", re.IGNORECASE)
TOKEN_PATTERN = re.compile(r"\b[A-Za-z][A-Za-z0-9\-]{1,}\b")
COMPOUND_TOKEN_PATTERN = re.compile(r"\b[A-Za-z][A-Za-z0-9_/-]{4,}\b")
STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "for",
    "from",
    "how",
    "in",
    "of",
    "on",
    "or",
    "show",
    "spec",
    "specification",
    "stage",
    "the",
    "document",
    "tr",
    "ts",
    "to",
    "what",
    "when",
    "where",
    "which",
    "with",
    "is",
    "defined",
    "end",
    "path",
    "paths",
}
INFERRED_SPEC_THRESHOLD = 2.0
MAX_SPEC_HINTS_PER_SPEC = 24
GENERIC_HINT_TERMS = {
    "general",
    "overview",
    "introduction",
    "procedure",
    "procedures",
    "message",
    "messages",
    "service",
    "services",
    "system",
    "network",
    "stage 2",
    "release 18",
    "inputs",
    "outputs",
    "semantics",
    "components",
    "cardinality",
    "operation definition",
    "information element definitions",
    "successful operation",
    "criticality",
    "yaml",
}
NOISY_HINT_PATTERN = re.compile(
    r"\b(?:sp-\d+[a-z]?|\d{2}-\d{4}|\d{4}-\d{2}|v\d+(?:\.\d+)+|release \d+|annex [a-z]|change history)\b",
    re.IGNORECASE,
)
GENERIC_QUERY_TOKENS = {"end", "path", "paths", "message", "messages", "procedure", "procedures"}


@dataclass
class QueryFeatureRegistry:
    aliases: dict[str, list[str]] = field(default_factory=dict)
    canonical_terms: dict[str, list[str]] = field(default_factory=dict)
    spec_term_hints: dict[str, dict[str, float]] = field(default_factory=dict)
    stopwords: set[str] = field(default_factory=lambda: set(STOPWORDS))

    @classmethod
    def from_json(cls, path: str | Path | None) -> QueryFeatureRegistry:
        if path is None:
            return cls()
        with Path(path).open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return cls(
            aliases={str(k): [str(v) for v in values] for k, values in payload.get("aliases", {}).items()},
            canonical_terms={
                str(k): [str(v) for v in values] for k, values in payload.get("canonical_terms", {}).items()
            },
            spec_term_hints={
                str(spec_no): {str(term): float(weight) for term, weight in terms.items()}
                for spec_no, terms in payload.get("spec_term_hints", {}).items()
            },
            stopwords=set(payload.get("stopwords", [])) or set(STOPWORDS),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "aliases": self.aliases,
            "canonical_terms": self.canonical_terms,
            "spec_term_hints": self.spec_term_hints,
            "stopwords": sorted(self.stopwords),
        }


@dataclass
class NormalizedQuery:
    raw_query: str
    normalized_query: str
    aliases: list[str] = field(default_factory=list)
    candidate_anchors: list[str] = field(default_factory=list)
    hinted_specs: list[str] = field(default_factory=list)
    inferred_specs: list[str] = field(default_factory=list)
    hinted_stages: list[str] = field(default_factory=list)
    stage_filters: list[str] = field(default_factory=list)
    query_vector: list[float] = field(default_factory=list)
    features: dict[str, list[str]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw_query": self.raw_query,
            "normalized_query": self.normalized_query,
            "aliases": self.aliases,
            "candidate_anchors": self.candidate_anchors,
            "hinted_specs": self.hinted_specs,
            "inferred_specs": self.inferred_specs,
            "hinted_stages": self.hinted_stages,
            "stage_filters": self.stage_filters,
            "query_vector": self.query_vector,
            "features": self.features,
        }


def normalize_text(query: str) -> str:
    return re.sub(r"\s+", " ", query.strip())


def extract_specs(query: str) -> list[str]:
    return sorted({match.group(1).replace(".", "") for match in SPEC_PATTERN.finditer(query)})


def extract_stages(query: str) -> list[str]:
    return sorted({match.group(1).title() for match in STAGE_PATTERN.finditer(query)})


def normalize_stage_filter(value: str) -> str:
    lowered = value.strip().lower().replace("-", "").replace("_", "").replace(" ", "")
    if lowered in {"stage2", "2"}:
        return "Stage 2"
    if lowered in {"stage3", "3"}:
        return "Stage 3"
    if lowered == "else":
        return "else"
    raise ValueError(f"Unsupported stage filter: {value}")


def extract_stage_filters(query: str) -> list[str]:
    filters = extract_stages(query)
    if ELSE_STAGE_PATTERN.search(query):
        filters.append("else")
    deduped: list[str] = []
    for item in filters:
        if item not in deduped:
            deduped.append(item)
    return deduped


def infer_specs(query: str, explicit_specs: list[str], registry: QueryFeatureRegistry) -> list[str]:
    if explicit_specs:
        return []
    lowered_variants = expand_query_match_variants(query)
    inferred: list[str] = []
    for spec_no, rules in registry.spec_term_hints.items():
        score = sum(weight for phrase, weight in rules.items() if any(phrase in variant for variant in lowered_variants))
        if score >= INFERRED_SPEC_THRESHOLD:
            inferred.append(spec_no)
    return sorted(inferred)


def normalize_hint_term(term: str) -> str:
    normalized = re.sub(r"\s+", " ", term.strip().lower())
    normalized = re.sub(r"^[^a-z0-9]+|[^a-z0-9]+$", "", normalized)
    return normalized


def expand_compound_variants(term: str) -> list[str]:
    variants: list[str] = []
    normalized = normalize_hint_term(term)
    if normalized:
        variants.append(normalized)
    split = re.sub(r"[_/]+", " ", term.strip())
    split = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", split)
    split_normalized = normalize_hint_term(split)
    if split_normalized and split_normalized not in variants:
        variants.append(split_normalized)
        split_tokens = split_normalized.split()
        for size in (4, 3):
            if len(split_tokens) >= size:
                suffix = " ".join(split_tokens[-size:])
                if suffix not in variants:
                    variants.append(suffix)
    return variants


def expand_query_match_variants(query: str) -> list[str]:
    variants = {query.lower()}
    variants.add(re.sub(r"([a-z]\d)([a-z]\d)", r"\1 \2", query.lower()))
    return sorted(variant for variant in variants if variant)


def iter_registry_terms(record: Any) -> list[tuple[str, float]]:
    weighted_terms: list[tuple[str, float]] = []
    for term, weight in (
        (record.clause_title, 2.5),
        (record.table_title, 2.1),
        (record.row_header, 2.2),
    ):
        for normalized in expand_compound_variants(term):
            weighted_terms.append((normalized, weight))
    for term in record.anchor_terms[:12]:
        for normalized in expand_compound_variants(term):
            weighted_terms.append((normalized, 1.6))
    for term in record.keywords[:8]:
        for normalized in expand_compound_variants(term):
            weighted_terms.append((normalized, 0.8))
    for token in COMPOUND_TOKEN_PATTERN.findall(record.embedding_text or record.text):
        if not any(ch.isdigit() for ch in token) and "_" not in token and not re.search(r"[A-Z].*[A-Z]", token):
            continue
        for normalized in expand_compound_variants(token):
            weighted_terms.append((normalized, 1.3))
    return weighted_terms


def build_spec_term_hints_from_corpus(
    input_path: str | Path,
    *,
    stopwords: set[str] | None = None,
    per_spec_limit: int = MAX_SPEC_HINTS_PER_SPEC,
) -> dict[str, dict[str, float]]:
    active_stopwords = stopwords or set(STOPWORDS)
    term_spec_weights: dict[str, Counter[str]] = defaultdict(Counter)
    spec_doc_counts: Counter[str] = Counter()

    with Path(input_path).open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = doc_record_from_dict(json.loads(line))
            if not record.spec_no:
                continue
            spec_doc_counts[record.spec_no] += 1
            seen_terms: set[str] = set()
            for term, weight in iter_registry_terms(record):
                if (
                    len(term) < 4
                    or term in GENERIC_HINT_TERMS
                    or term in active_stopwords
                    or NOISY_HINT_PATTERN.search(term)
                    or (len(term.split()) == 1 and term.islower())
                    or all(token in active_stopwords for token in term.split())
                ):
                    continue
                if term in seen_terms:
                    continue
                seen_terms.add(term)
                term_spec_weights[term][record.spec_no] += weight

    spec_count = max(len(spec_doc_counts), 1)
    ranked_terms_by_spec: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for term, weights_by_spec in term_spec_weights.items():
        spread = len(weights_by_spec)
        if spread == 0 or spread > max(3, spec_count // 2):
            continue
        idf = math.log1p(spec_count / spread)
        for spec_no, tf in weights_by_spec.items():
            score = tf * idf
            if score < 2.2:
                continue
            ranked_terms_by_spec[spec_no].append((term, round(score, 3)))

    return {
        spec_no: {term: score for term, score in sorted(terms, key=lambda item: (-item[1], item[0]))[:per_spec_limit]}
        for spec_no, terms in ranked_terms_by_spec.items()
    }


def build_query_feature_registry_from_corpus(
    input_path: str | Path,
    *,
    aliases: dict[str, list[str]] | None = None,
    canonical_terms: dict[str, list[str]] | None = None,
    stopwords: set[str] | None = None,
) -> QueryFeatureRegistry:
    active_stopwords = stopwords or set(STOPWORDS)
    return QueryFeatureRegistry(
        aliases=aliases or {},
        canonical_terms=canonical_terms or {},
        spec_term_hints=build_spec_term_hints_from_corpus(input_path, stopwords=active_stopwords),
        stopwords=active_stopwords,
    )


def extract_aliases(query: str, registry: QueryFeatureRegistry) -> list[str]:
    aliases = {alias for alias in ALIAS_PATTERN.findall(query) if alias.lower() not in registry.stopwords}
    tokens = TOKEN_PATTERN.findall(query)
    for size in (2, 3):
        for idx in range(0, max(0, len(tokens) - size + 1)):
            phrase_tokens = tokens[idx : idx + size]
            if not any(char.isdigit() for char in phrase_tokens[0]):
                continue
            if any(token.lower() in registry.stopwords for token in phrase_tokens[1:]):
                continue
            compound = phrase_tokens[0] + "".join(token[:1].upper() + token[1:] for token in phrase_tokens[1:])
            aliases.add(compound)
    lowered = query.lower()
    for canonical, expansions in registry.aliases.items():
        if canonical.lower() in lowered or any(item.lower() in lowered for item in expansions):
            aliases.add(canonical)
            aliases.update(expansions)
    return sorted(aliases)


def extract_keyword_tokens(query: str, registry: QueryFeatureRegistry) -> list[str]:
    tokens = []
    for token in TOKEN_PATTERN.findall(query):
        lowered = token.lower()
        if lowered in registry.stopwords:
            continue
        if lowered in GENERIC_QUERY_TOKENS and len(TOKEN_PATTERN.findall(query)) > 2:
            continue
        if len(lowered) < 3 and not token.isupper():
            continue
        tokens.append(token)
    return tokens


def extract_anchor_candidates(query: str, registry: QueryFeatureRegistry) -> list[str]:
    tokens = extract_keyword_tokens(query, registry)
    raw_tokens = TOKEN_PATTERN.findall(query)
    candidates = set(tokens)
    if len(raw_tokens) >= 4:
        full_phrase = " ".join(raw_tokens)
        candidates.add(full_phrase)
    for size in (2, 3, 4, 5, 6):
        for idx in range(0, max(0, len(tokens) - size + 1)):
            phrase = " ".join(tokens[idx : idx + size])
            if len(phrase) >= 5:
                candidates.add(phrase)
    lowered = query.lower()
    for canonical, variants in registry.canonical_terms.items():
        if canonical.lower() in lowered or any(variant.lower() in lowered for variant in variants):
            candidates.add(canonical)
            candidates.update(variants)
    ranked = sorted(
        candidates,
        key=lambda item: (
            -min(len(item.split()), 6),
            -len(item),
            item.lower(),
        ),
    )
    return ranked


def normalize_query(
    query: str,
    registry: QueryFeatureRegistry | None = None,
    query_vector: list[float] | None = None,
    stage_filters: list[str] | None = None,
) -> NormalizedQuery:
    active_registry = registry or QueryFeatureRegistry()
    normalized = normalize_text(query)
    aliases = extract_aliases(normalized, active_registry)
    hinted_specs = extract_specs(normalized)
    inferred_specs = infer_specs(normalized, hinted_specs, active_registry)
    hinted_stages = extract_stages(normalized)
    explicit_stage_filters = [normalize_stage_filter(item) for item in (stage_filters or [])]
    merged_stage_filters = extract_stage_filters(normalized)
    for item in explicit_stage_filters:
        if item not in merged_stage_filters:
            merged_stage_filters.append(item)
    candidate_anchors = extract_anchor_candidates(normalized, active_registry)
    return NormalizedQuery(
        raw_query=query,
        normalized_query=normalized,
        aliases=aliases,
        candidate_anchors=candidate_anchors,
        hinted_specs=hinted_specs,
        inferred_specs=inferred_specs,
        hinted_stages=hinted_stages,
        stage_filters=merged_stage_filters,
        query_vector=query_vector or [],
        features={
            "aliases": aliases,
            "hinted_specs": hinted_specs,
            "inferred_specs": inferred_specs,
            "hinted_stages": hinted_stages,
            "stage_filters": merged_stage_filters,
            "candidate_anchors": candidate_anchors,
            "tokens": extract_keyword_tokens(normalized, active_registry),
        },
    )
