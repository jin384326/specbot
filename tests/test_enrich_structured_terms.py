from __future__ import annotations

import json
from pathlib import Path

from enrich.enrich_metadata import enrich_corpus


def test_enrich_corpus_emits_entity_docs_and_structured_terms(tmp_path: Path) -> None:
    source = tmp_path / "corpus.jsonl"
    source.write_text(
        json.dumps(
            {
                "doc_id": "23502:clause:4.3.2",
                "doc_type": "clause_doc",
                "content_kind": "clause",
                "spec_no": "23502",
                "spec_title": "Procedures",
                "clause_id": "4.3.2",
                "clause_title": "PDU Session Establishment procedure",
                "text": "The PDU Session ID IE is included in the PDU Session Resource Setup Request message. The ueCapabilityTransfer procedure may follow.",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    output = tmp_path / "enriched.jsonl"

    count = enrich_corpus(source, output)

    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert count == len(rows)
    clause_row = next(row for row in rows if row["doc_type"] == "clause_doc")
    entity_rows = [row for row in rows if row["doc_type"] == "entity_doc"]

    assert "PDU Session ID IE" in clause_row["ie_names"]
    assert "PDU Session Resource Setup Request message" in clause_row["message_names"]
    assert "ueCapabilityTransfer" in clause_row["camel_case_identifiers"]
    assert entity_rows
    assert {row["entity_type"] for row in entity_rows} == {"ie_name", "message_name"}
