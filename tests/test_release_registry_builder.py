from __future__ import annotations

import json
from pathlib import Path

from app.release_registry_builder import merge_records_by_doc_id, write_release_registries


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=True) + "\n")


def base_record(doc_id: str, spec_no: str, release_data: str, release: str, clause_title: str) -> dict:
    return {
        "doc_id": doc_id,
        "doc_type": "clause_doc",
        "content_kind": "clause",
        "spec_no": spec_no,
        "spec_title": "Dummy spec",
        "release": release,
        "release_data": release_data,
        "series": spec_no[:2],
        "ts_or_tr": "TS",
        "stage_hint": "Stage 3",
        "clause_id": doc_id.split(":")[-1],
        "clause_title": clause_title,
        "clause_path": [doc_id.split(":")[-1]],
        "parent_clause_id": "",
        "text": f"{clause_title} body text",
        "summary": "",
        "retrieval_weight": 1.0,
        "keywords": [clause_title.lower()],
        "anchor_terms": [clause_title],
        "ie_names": [],
        "message_names": [],
        "procedure_names": [],
        "table_headers": [],
        "acronyms": [],
        "camel_case_identifiers": [],
        "referenced_specs": [],
        "referenced_clauses": [],
        "source_file": f"Specs/{release_data}/{release}/{spec_no}-i90.docx",
        "table_title": "",
        "order_in_source": 1,
        "version_tag": "i90",
        "domain_hint": [],
        "embedding_text": f"{clause_title} body text",
        "embedding_model": "",
        "embedding_dim": 0,
        "dense_vector": [],
        "table_id": "",
        "row_index": 0,
        "row_header": "",
        "row_cells": [],
        "table_raw": [],
        "table_markdown": "",
        "passage_id": "",
        "passage_index": 0,
        "paragraph_start_index": 0,
        "paragraph_end_index": 0,
        "entity_type": "",
        "entity_name": "",
        "source_doc_id": "",
    }


def test_write_release_registries_creates_global_and_grouped_outputs(tmp_path: Path) -> None:
    enriched = tmp_path / "enriched.jsonl"
    write_jsonl(
        enriched,
        [
            base_record("23501:clause:4.1", "23501", "2025-12", "Rel-18", "Session Management"),
            base_record("29512:clause:A.2", "29512", "2024-12", "Rel-18", "Npcf_SMPolicyControl API"),
        ],
    )

    global_output = tmp_path / "spec_query_registry.json"
    output_root = tmp_path / "registries"
    summary = write_release_registries(input_paths=[enriched], global_output=global_output, output_root=output_root)

    assert summary["merged_records"] == 2
    assert summary["group_count"] == 2
    assert global_output.exists()
    assert (output_root / "2025-12" / "Rel-18" / "spec_query_registry.json").exists()
    assert (output_root / "2024-12" / "Rel-18" / "spec_query_registry.json").exists()


def test_write_release_registries_last_input_wins_for_same_doc_id(tmp_path: Path) -> None:
    base = tmp_path / "base.jsonl"
    overlay = tmp_path / "overlay.jsonl"
    write_jsonl(base, [base_record("23501:clause:4.1", "23501", "2025-12", "Rel-18", "Old Title")])
    write_jsonl(overlay, [base_record("23501:clause:4.1", "23501", "2025-12", "Rel-18", "New Title")])

    merged = merge_records_by_doc_id([base, overlay])
    assert len(merged) == 1
    assert merged[0]["clause_title"] == "New Title"
