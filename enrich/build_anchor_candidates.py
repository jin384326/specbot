from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from enrich.enrich_metadata import extract_abbreviation_pairs, load_jsonl
from parser.models import DocRecord

GENERIC_TERMS = {
    "general",
    "introduction",
    "overview",
    "procedure",
    "description",
    "parameters",
    "message",
    "messages",
    "information",
    "network",
    "service",
    "requirements",
}
TRAILING_GENERIC_WORDS = {"handling", "procedures", "procedure", "values", "value", "support"}


@dataclass
class CandidateScore:
    term: str
    total_score: float
    classification: str
    source_breakdown: dict[str, float] = field(default_factory=dict)
    spec_count: int = 0
    doc_count: int = 0


def normalize_term(term: str) -> str:
    return re.sub(r"\s+", " ", term.strip())


def expand_term_variants(term: str) -> list[str]:
    normalized = normalize_term(term)
    variants = {normalized}
    tokens = normalized.split()
    if len(tokens) >= 2 and tokens[-1].lower() in TRAILING_GENERIC_WORDS:
        variants.add(" ".join(tokens[:-1]))
    return sorted(variant for variant in variants if variant)


def classify_score(score: float) -> str:
    if score >= 4.5:
        return "strong"
    if score >= 2.0:
        return "normal"
    return "reject"


def collect_doc_terms(record: DocRecord) -> list[tuple[str, str]]:
    terms: list[tuple[str, str]] = []
    if record.clause_title:
        for variant in expand_term_variants(record.clause_title):
            terms.append((variant, "clause_title"))
    if record.table_title:
        for variant in expand_term_variants(record.table_title):
            terms.append((variant, "table_title"))
    if record.row_header:
        for variant in expand_term_variants(record.row_header):
            terms.append((variant, "row_header"))
    for long_form, short_form in extract_abbreviation_pairs(record.text):
        terms.append((long_form, "abbreviation_long"))
        terms.append((short_form, "abbreviation_short"))
    for cell in record.row_cells:
        if cell:
            terms.append((cell, "row_value"))
    return [(normalize_term(term), source) for term, source in terms if normalize_term(term)]


def score_anchor_candidates(records: Iterable[DocRecord]) -> list[dict]:
    term_sources: dict[str, Counter[str]] = defaultdict(Counter)
    term_specs: dict[str, set[str]] = defaultdict(set)
    term_docs: dict[str, set[str]] = defaultdict(set)
    base_weights = {
        "clause_title": 2.0,
        "table_title": 1.8,
        "row_header": 1.7,
        "abbreviation_long": 1.2,
        "abbreviation_short": 1.5,
        "row_value": 0.4,
    }

    for record in records:
        for term, source in collect_doc_terms(record):
            if len(term) < 3:
                continue
            term_sources[term][source] += 1
            if record.spec_no:
                term_specs[term].add(record.spec_no)
            term_docs[term].add(record.doc_id)

    candidates: list[dict] = []
    for term, source_counts in term_sources.items():
        breakdown: dict[str, float] = {}
        total_score = 0.0
        for source, count in source_counts.items():
            contribution = base_weights.get(source, 0.0) * min(count, 3)
            breakdown[source] = round(contribution, 3)
            total_score += contribution

        spec_count = len(term_specs[term])
        doc_count = len(term_docs[term])
        if spec_count > 1:
            bonus = min(2.0, 0.6 * (spec_count - 1))
            breakdown["cross_spec_bonus"] = round(bonus, 3)
            total_score += bonus
        if term.lower() in GENERIC_TERMS:
            breakdown["generic_penalty"] = -2.5
            total_score -= 2.5
        if len(term.split()) == 1 and term.islower():
            breakdown["single_token_penalty"] = -0.5
            total_score -= 0.5

        result = CandidateScore(
            term=term,
            total_score=round(total_score, 3),
            classification=classify_score(total_score),
            source_breakdown=breakdown,
            spec_count=spec_count,
            doc_count=doc_count,
        )
        candidates.append(
            {
                "term": result.term,
                "score": result.total_score,
                "classification": result.classification,
                "source_breakdown": result.source_breakdown,
                "spec_count": result.spec_count,
                "doc_count": result.doc_count,
            }
        )
    return sorted(candidates, key=lambda item: (-item["score"], item["term"].lower()))


def build_anchor_candidates(input_path: str | Path, output_path: str | Path) -> list[dict]:
    records = load_jsonl(input_path)
    candidates = score_anchor_candidates(records)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for item in candidates:
            handle.write(json.dumps(item, ensure_ascii=True) + "\n")
    return candidates
