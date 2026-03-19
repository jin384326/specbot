from __future__ import annotations

from parser.models import DocRecord


def _join_non_empty(parts: list[str]) -> str:
    return "\n".join(part for part in parts if part).strip()


def build_embedding_text_for_record(record: DocRecord) -> str:
    if record.doc_type == "entity_doc":
        return _join_non_empty(
            [
                record.spec_no,
                record.spec_title,
                record.entity_type,
                record.entity_name,
                record.clause_id,
                record.clause_title,
                record.row_header,
                record.text,
            ]
        )
    if record.doc_type == "table_row_doc":
        return _join_non_empty(
            [
                record.spec_no,
                record.spec_title,
                record.clause_id,
                record.clause_title,
                record.table_title,
                " | ".join(record.table_headers),
                record.row_header,
                " | ".join(record.row_cells),
                record.text,
            ]
        )
    if record.doc_type == "table_doc":
        return _join_non_empty(
            [
                record.spec_no,
                record.spec_title,
                record.clause_id,
                record.clause_title,
                record.table_title,
                " | ".join(record.table_headers),
                record.text,
            ]
        )
    return _join_non_empty(
        [
            record.spec_no,
            record.spec_title,
            record.clause_id,
            record.clause_title,
            " ".join(record.ie_names),
            " ".join(record.message_names),
            " ".join(record.procedure_names),
            record.text,
        ]
    )
