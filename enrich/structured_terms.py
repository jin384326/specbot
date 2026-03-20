from __future__ import annotations

import re
import unicodedata
from typing import Iterable

from embedding.text_builders import build_embedding_text_for_record
from parser.models import DocRecord, EntityDoc

_ZERO_WIDTH_RE = re.compile(r"[\u200b-\u200f\ufeff\u2060]")

ABBREVIATION_TOKEN_PATTERN = re.compile(r"\b[A-Z][A-Z0-9\-]{1,}\b")
CAMEL_CASE_PATTERN = re.compile(r"\b[a-z]+(?:[A-Z][a-z0-9]+){1,}\b|\b[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]+){1,}\b")
IE_NAME_PATTERN = re.compile(
    r"\b([A-Z][A-Za-z0-9/\-]*(?:\s+[A-Z][A-Za-z0-9/\-]*)*\s+(?:IE|information element))\b"
)
PROCEDURE_NAME_PATTERN = re.compile(
    r"\b([A-Z0-9][A-Za-z0-9/\-]*(?:\s+[A-Z0-9][A-Za-z0-9/\-]*)*\s+procedures?)\b",
    re.IGNORECASE,
)


def normalize_space(text: str) -> str:
    t = unicodedata.normalize("NFKC", text or "")
    t = _ZERO_WIDTH_RE.sub("", t)
    return re.sub(r"\s+", " ", t).strip()


def _term_fingerprint(text: str) -> str:
    """Match parser.table cell dedupe: ignore whitespace so visually identical labels collapse."""
    return re.sub(r"\s+", "", normalize_space(text).lower())


def dedupe_terms(terms: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for term in terms:
        candidate = normalize_space(term)
        candidate = re.sub(r"^(?:the|a|an)\s+", "", candidate, flags=re.IGNORECASE)
        if not candidate:
            continue
        key = _term_fingerprint(candidate)
        if key in seen:
            continue
        seen.add(key)
        result.append(candidate)
    return result


def collect_source_texts(record: DocRecord) -> list[str]:
    return [
        record.clause_title,
        record.table_title,
        record.row_header,
        record.text,
        " ".join(record.row_cells),
    ]


def extract_table_headers(record: DocRecord) -> list[str]:
    if record.table_headers:
        return dedupe_terms(record.table_headers)
    if record.table_raw:
        return dedupe_terms(record.table_raw[0])
    return []


def extract_acronyms(record: DocRecord) -> list[str]:
    terms: list[str] = []
    for text in collect_source_texts(record):
        terms.extend(match.group(0) for match in ABBREVIATION_TOKEN_PATTERN.finditer(text))
    return dedupe_terms(terms)


def extract_camel_case_identifiers(record: DocRecord) -> list[str]:
    terms: list[str] = []
    for text in collect_source_texts(record):
        terms.extend(match.group(0) for match in CAMEL_CASE_PATTERN.finditer(text))
    return dedupe_terms(terms)


def extract_ie_names(record: DocRecord) -> list[str]:
    terms: list[str] = []
    for text in collect_source_texts(record):
        terms.extend(match.group(1) for match in IE_NAME_PATTERN.finditer(text))
    return dedupe_terms(terms)


def extract_message_names(record: DocRecord) -> list[str]:
    terms: list[str] = []
    for text in collect_source_texts(record):
        tokens = normalize_space(text).split()
        for index, token in enumerate(tokens):
            lowered = token.lower().rstrip(".,;:")
            if lowered not in {
                "request",
                "response",
                "accept",
                "reject",
                "command",
                "complete",
                "transfer",
                "notification",
                "indication",
                "message",
            }:
                continue
            start = index
            while start > 0:
                previous = tokens[start - 1].strip(".,;:()")
                if previous and (previous[0].isupper() or any(ch.isdigit() for ch in previous)):
                    start -= 1
                    continue
                break
            candidate = " ".join(token.strip(".,;:()") for token in tokens[start : index + 1]).strip()
            if candidate and " " in candidate:
                terms.append(candidate)
    return dedupe_terms(terms)


def extract_procedure_names(record: DocRecord) -> list[str]:
    terms: list[str] = []
    for text in collect_source_texts(record):
        terms.extend(match.group(1) for match in PROCEDURE_NAME_PATTERN.finditer(text))
    return dedupe_terms(terms)


def collect_structured_terms(record: DocRecord) -> dict[str, list[str]]:
    return {
        "ie_names": extract_ie_names(record),
        "message_names": extract_message_names(record),
        "procedure_names": extract_procedure_names(record),
        "table_headers": extract_table_headers(record),
        "acronyms": extract_acronyms(record),
        "camel_case_identifiers": extract_camel_case_identifiers(record),
    }


def build_entity_docs(record: DocRecord) -> list[EntityDoc]:
    entity_docs: list[EntityDoc] = []
    for entity_type, terms in (("ie_name", record.ie_names), ("message_name", record.message_names)):
        for index, term in enumerate(terms):
            payload = record.to_dict()
            payload.update(
                {
                    "doc_id": f"{record.doc_id}:entity:{entity_type}:{index}",
                    "doc_type": "entity_doc",
                    "content_kind": "entity",
                    "entity_type": entity_type,
                    "entity_name": term,
                    "source_doc_id": record.doc_id,
                    "text": term,
                    "summary": record.clause_title,
                    "anchor_terms": dedupe_terms([term, *record.acronyms, *record.camel_case_identifiers]),
                    "keywords": dedupe_terms([term, *record.keywords[:4]]),
                    "dense_vector": [],
                    "embedding_model": "",
                    "embedding_dim": 0,
                }
            )
            entity_doc = EntityDoc(**payload)
            entity_doc.embedding_text = build_embedding_text_for_record(entity_doc)
            entity_docs.append(entity_doc)
    return entity_docs
