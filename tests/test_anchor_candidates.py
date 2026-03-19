from __future__ import annotations

from enrich.build_anchor_candidates import score_anchor_candidates
from parser.models import ClauseDoc, TableRowDoc


def test_anchor_candidate_scoring() -> None:
    records = [
        ClauseDoc(
            doc_id="23501:clause:4.3.2",
            spec_no="23501",
            clause_id="4.3.2",
            clause_title="SSC mode handling",
            text="Session and Service Continuity (SSC) mode is used in PDU session handling.",
        ),
        TableRowDoc(
            doc_id="23502:table:1:row:1",
            spec_no="23502",
            clause_id="6.3.2",
            clause_title="PDU session procedures",
            table_title="SSC mode values",
            row_header="SSC mode",
            row_cells=["SSC mode", "1"],
            text="SSC mode: 1",
        ),
    ]
    results = score_anchor_candidates(records)
    by_term = {item["term"]: item for item in results}

    assert by_term["SSC mode"]["classification"] in {"strong", "normal"}
    assert by_term["SSC"]["source_breakdown"]["abbreviation_short"] > 0
    assert by_term["SSC mode"]["spec_count"] == 2
