from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from enrich.enrich_metadata import iter_jsonl
from parser.models import DocRecord


def doc_record_to_vespa_feed(record: DocRecord) -> dict:
    if record.doc_type == "table_doc":
        searchable_text = record.text
    elif record.doc_type == "table_row_doc":
        searchable_text = record.text or "; ".join(record.row_cells)
    else:
        searchable_text = record.embedding_text or record.text

    fields = {
        "doc_id": record.doc_id,
        "doc_type": record.doc_type,
        "content_kind": record.content_kind,
        "spec_no": record.spec_no,
        "spec_title": record.spec_title,
        "release": record.release,
        "release_data": record.release_data,
        "series": record.series,
        "ts_or_tr": record.ts_or_tr,
        "stage_hint": record.stage_hint,
        "clause_id": record.clause_id,
        "clause_title": record.clause_title,
        "clause_path": record.clause_path,
        "parent_clause_id": record.parent_clause_id,
        "text": searchable_text,
        "summary_text": record.summary,
        "retrieval_weight": record.retrieval_weight,
        "keywords": record.keywords,
        "anchor_terms": record.anchor_terms,
        "ie_names": record.ie_names,
        "message_names": record.message_names,
        "procedure_names": record.procedure_names,
        "table_headers": record.table_headers,
        "acronyms": record.acronyms,
        "camel_case_identifiers": record.camel_case_identifiers,
        "referenced_specs": record.referenced_specs,
        "referenced_clauses": record.referenced_clauses,
        "source_file": record.source_file,
        "table_title": record.table_title,
        "order_in_source": record.order_in_source,
        "version_tag": record.version_tag,
        "domain_hint": record.domain_hint,
        "embedding_text": record.embedding_text,
        "embedding_model": record.embedding_model,
        "embedding_dim": record.embedding_dim,
        "dense_embedding": {"values": record.dense_vector} if record.dense_vector else None,
        "table_id": record.table_id,
        "row_index": record.row_index,
        "row_header": record.row_header,
        "row_cells": record.row_cells,
        "table_raw_json": json.dumps(record.table_raw, ensure_ascii=True),
        "table_markdown": record.table_markdown,
        "passage_id": record.passage_id,
        "passage_index": record.passage_index,
        "paragraph_start_index": record.paragraph_start_index,
        "paragraph_end_index": record.paragraph_end_index,
        "entity_type": record.entity_type,
        "entity_name": record.entity_name,
        "source_doc_id": record.source_doc_id,
    }
    return {
        "put": f"id:spec_finder:doc::{record.doc_id}",
        "fields": {key: value for key, value in fields.items() if value is not None},
    }


def export_corpus_to_vespa_feed(input_path: str | Path, output_path: str | Path) -> int:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    return write_vespa_feed(iter_jsonl(input_path), output)


def write_vespa_feed(records: Iterable[DocRecord], output_path: str | Path) -> int:
    output = Path(output_path)
    count = 0
    with output.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(doc_record_to_vespa_feed(record), ensure_ascii=True) + "\n")
            count += 1
    return count
