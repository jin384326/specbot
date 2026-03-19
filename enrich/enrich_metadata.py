from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Iterable, Iterator

from embedding.text_builders import build_embedding_text_for_record
from enrich.structured_terms import build_entity_docs, collect_structured_terms, dedupe_terms
from parser.models import DocRecord, doc_record_from_dict

WORD_PATTERN = re.compile(r"\b[A-Za-z][A-Za-z0-9\-]{2,}\b")
CLAUSE_REF_PATTERN = re.compile(r"\b\d+(?:\.\d+)*(?:[A-Za-z])?\b")
SPEC_REF_PATTERN = re.compile(r"\b(?:3GPP\s+)?(?:TS|TR)\s+(\d{2}\.\d{3}|\d{5})\b")
ABBREV_PATTERN = re.compile(r"\b(?P<long>[A-Za-z][A-Za-z0-9\-/ ]{3,}?)\s*\((?P<short>[A-Z][A-Z0-9\-]{1,})\)")
STOPWORDS = {
    "shall",
    "should",
    "that",
    "with",
    "this",
    "from",
    "have",
    "when",
    "into",
    "between",
    "table",
    "clause",
    "figure",
    "support",
    "stage",
    "release",
}
LOW_SIGNAL_CLAUSE_TITLES = {"references", "foreword", "contents", "scope"}


def load_jsonl(path: str | Path) -> list[DocRecord]:
    records: list[DocRecord] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                records.append(doc_record_from_dict(json.loads(line)))
    return records


def iter_jsonl(path: str | Path) -> Iterator[DocRecord]:
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield doc_record_from_dict(json.loads(line))


def save_jsonl(records: Iterable[DocRecord], path: str | Path) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record.to_dict(), ensure_ascii=True) + "\n")


def extract_keywords(text: str, limit: int = 12) -> list[str]:
    counts = Counter(
        word.lower()
        for word in WORD_PATTERN.findall(text)
        if word.lower() not in STOPWORDS and not word.isdigit()
    )
    return [token for token, _ in counts.most_common(limit)]


def extract_abbreviation_pairs(text: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for match in ABBREV_PATTERN.finditer(text):
        long_form = normalize_space(match.group("long"))
        short_form = match.group("short").strip()
        if len(long_form.split()) >= 2:
            pairs.append((long_form, short_form))
    return pairs


def extract_referenced_clauses(text: str) -> list[str]:
    return sorted(
        {
            match.group(0)
            for match in CLAUSE_REF_PATTERN.finditer(text)
            if "." in match.group(0)
        }
    )


def extract_referenced_specs(text: str) -> list[str]:
    return sorted({match.group(1).replace(".", "") for match in SPEC_REF_PATTERN.finditer(text)})


def load_taxonomy(taxonomy_path: str | Path | None) -> dict[str, list[str]]:
    if taxonomy_path is None:
        return {}
    with Path(taxonomy_path).open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return {str(key): [str(value).lower() for value in values] for key, values in payload.items()}


def infer_domain_hints(text: str, taxonomy: dict[str, list[str]]) -> list[str]:
    lowered = text.lower()
    hints = [label for label, terms in taxonomy.items() if any(term in lowered for term in terms)]
    return sorted(set(hints))


def build_embedding_text(record: DocRecord) -> str:
    return build_embedding_text_for_record(record)


def infer_retrieval_weight(record: DocRecord) -> float:
    title = normalize_space(record.clause_title).lower()
    if record.clause_id.startswith("front_matter_"):
        return 0.2
    if title in LOW_SIGNAL_CLAUSE_TITLES and record.doc_type in {"clause_doc", "passage_doc"}:
        return 0.35 if title == "references" else 0.55
    if record.doc_type == "table_row_doc":
        return 1.35
    if record.doc_type == "table_doc":
        return 1.15
    if record.doc_type == "passage_doc":
        return 1.1
    return 1.0


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def enrich_record(record: DocRecord, taxonomy: dict[str, list[str]] | None = None) -> DocRecord:
    text = normalize_space(record.text)
    title_text = " ".join(part for part in [record.clause_title, record.table_title, record.row_header] if part)
    keyword_source = f"{title_text} {text}".strip()
    record.keywords = extract_keywords(keyword_source)

    pairs = extract_abbreviation_pairs(text)
    anchor_terms = set(record.anchor_terms)
    for long_form, short_form in pairs:
        anchor_terms.add(long_form)
        anchor_terms.add(short_form)
    for item in record.keywords[:8]:
        anchor_terms.add(item)
    if record.table_title:
        anchor_terms.add(record.table_title)
    if record.row_header:
        anchor_terms.add(record.row_header)
    structured_terms = collect_structured_terms(record)
    record.ie_names = structured_terms["ie_names"]
    record.message_names = structured_terms["message_names"]
    record.procedure_names = structured_terms["procedure_names"]
    record.table_headers = structured_terms["table_headers"]
    record.acronyms = structured_terms["acronyms"]
    record.camel_case_identifiers = structured_terms["camel_case_identifiers"]
    for term in [
        *record.ie_names,
        *record.message_names,
        *record.procedure_names,
        *record.table_headers,
        *record.acronyms,
        *record.camel_case_identifiers,
    ]:
        anchor_terms.add(term)
    record.anchor_terms = sorted(dedupe_terms(anchor_terms))
    record.referenced_clauses = sorted(set(record.referenced_clauses) | set(extract_referenced_clauses(text)))
    record.referenced_specs = sorted(set(record.referenced_specs) | set(extract_referenced_specs(text)))
    record.domain_hint = infer_domain_hints(text, taxonomy or {}) if taxonomy else []
    record.embedding_text = build_embedding_text(record)
    record.retrieval_weight = infer_retrieval_weight(record)
    return record


def enrich_corpus(
    input_path: str | Path,
    output_path: str | Path,
    taxonomy_path: str | Path | None = None,
) -> int:
    taxonomy = load_taxonomy(taxonomy_path)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with output.open("w", encoding="utf-8") as handle:
        for record in iter_jsonl(input_path):
            enriched = enrich_record(record, taxonomy=taxonomy)
            handle.write(json.dumps(enriched.to_dict(), ensure_ascii=True) + "\n")
            count += 1
            for entity_doc in build_entity_docs(enriched):
                handle.write(json.dumps(entity_doc.to_dict(), ensure_ascii=True) + "\n")
                count += 1
    return count
