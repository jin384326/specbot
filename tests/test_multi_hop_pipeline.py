from __future__ import annotations

from parser.models import ClauseDoc, TableRowDoc
from retrieval.multi_hop_pipeline import InMemoryMultiHopBackend, MultiHopRetrievalPipeline


def test_multi_hop_pipeline_prefers_structured_anchors_and_merges_by_clause() -> None:
    records = [
        ClauseDoc(
            doc_id="23502:clause:4.3.2",
            spec_no="23502",
            stage_hint="Stage 3",
            clause_id="4.3.2",
            clause_title="PDU Session Establishment procedure",
            text="The PDU Session ID IE is included in the PDU Session Resource Setup Request message.",
            ie_names=["PDU Session ID IE"],
            message_names=["PDU Session Resource Setup Request message"],
            procedure_names=["PDU Session Establishment procedure"],
            anchor_terms=["PDU Session ID IE", "PDU Session Resource Setup Request message"],
            embedding_text="PDU Session Establishment procedure PDU Session ID IE",
        ),
        TableRowDoc(
            doc_id="38413:table:1:row:1",
            spec_no="38413",
            stage_hint="else",
            clause_id="8.2.1",
            clause_title="RRC procedures",
            table_title="Message mapping",
            row_header="PDU Session Resource Setup Request message",
            row_cells=["PDU Session Resource Setup Request message", "RRC Reconfiguration"],
            message_names=["PDU Session Resource Setup Request message"],
            anchor_terms=["PDU Session Resource Setup Request message"],
            embedding_text="PDU Session Resource Setup Request message RRC Reconfiguration",
            text="PDU Session Resource Setup Request message maps to RRC Reconfiguration.",
        ),
    ]

    pipeline = MultiHopRetrievalPipeline(InMemoryMultiHopBackend(records))
    result = pipeline.run("Where is PDU Session Resource Setup Request defined", limit=5)

    assert result["selected_anchors"]
    assert any(anchor["anchor"] == "PDU Session Resource Setup Request message" for anchor in result["selected_anchors"])
    assert result["merged_clauses"][0]["spec_no"] in {"23502", "38413"}


def test_multi_hop_pipeline_filters_unrelated_anchors_for_phrase_query() -> None:
    records = [
        ClauseDoc(
            doc_id="23501:clause:5.33.2.1",
            spec_no="23501",
            stage_hint="Stage 2",
            clause_id="5.33.2.1",
            clause_title="Dual Connectivity based end to end Redundant User Plane Paths",
            text="This clause describes End to End Redundant Paths for user plane handling.",
            anchor_terms=["End to End Redundant Paths"],
            embedding_text="End to End Redundant Paths",
        ),
        ClauseDoc(
            doc_id="23501:clause:5.10.3",
            spec_no="23501",
            stage_hint="Stage 2",
            clause_id="5.10.3",
            clause_title="PDU Session User Plane Security",
            text="PDU Session Establishment Request handling is described here.",
            message_names=["PDU Session Establishment Request"],
            anchor_terms=["PDU Session Establishment Request"],
            embedding_text="PDU Session Establishment Request",
        ),
    ]

    pipeline = MultiHopRetrievalPipeline(InMemoryMultiHopBackend(records))
    result = pipeline.run("End to End Redundant Paths", limit=5)

    assert result["merged_clauses"][0]["clause_id"] == "5.33.2.1"
    assert all("PDU Session Establishment Request" != anchor["anchor"] for anchor in result["selected_anchors"])


def test_in_memory_backend_prefers_clause_title_phrase_matches_over_body_mentions() -> None:
    records = [
        ClauseDoc(
            doc_id="23501:clause:5.33.2.1",
            spec_no="23501",
            stage_hint="Stage 2",
            clause_id="5.33.2.1",
            clause_title="Dual Connectivity based end to end Redundant User Plane Paths",
            text="This clause describes user plane paths.",
            embedding_text="Dual Connectivity based end to end Redundant User Plane Paths",
        ),
        ClauseDoc(
            doc_id="23502:clause:4.2.3.2",
            spec_no="23502",
            stage_hint="Stage 2",
            clause_id="4.2.3.2",
            clause_title="UE Triggered Service Request",
            text="This body mentions End to End Redundant Paths once.",
            embedding_text="This body mentions End to End Redundant Paths once.",
        ),
    ]

    hits = InMemoryMultiHopBackend(records).search(["End to End Redundant Paths"], limit=5)

    assert hits[0].doc.doc_id == "23501:clause:5.33.2.1"
