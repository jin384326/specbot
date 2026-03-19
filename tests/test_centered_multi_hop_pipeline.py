from __future__ import annotations

from parser.models import ClauseDoc
from retrieval.centered_multi_hop_pipeline import CenteredMultiHopRetrievalPipeline
from retrieval.multi_hop_pipeline import InMemoryMultiHopBackend
from retrieval.stage_router import build_routing_index, infer_entry_specs, resolve_spec_stage_filters


class FakeSelector:
    def select_specs(self, query_text: str, candidates: list[dict], limit: int = 6) -> list[str]:
        del query_text, limit
        selected = [item["spec_id"] for item in candidates[:2]]
        return selected + ["invented-spec-id"]

    def judge_relevance(self, query_text: str, candidates: list[dict], limit: int = 6) -> list[str]:
        del query_text, limit
        allowed = {item["doc_id"] for item in candidates}
        selected = ["23501:clause:5.33.2.1", "invented-doc-id"]
        return [item for item in selected if item in allowed]

    def select_anchors(self, query_text: str, candidates: list[dict], limit: int = 6) -> list[str]:
        del query_text, limit
        selected = [item["anchor_id"] for item in candidates[:1]]
        return selected + ["invented-anchor-id"]


def test_centered_pipeline_prefers_23501_seed_and_filters_llm_outputs() -> None:
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
            doc_id="38413:clause:9.3.1.136",
            spec_no="38413",
            stage_hint="else",
            clause_id="9.3.1.136",
            clause_title="Redundant PDU Session Information",
            text="This IE carries redundant PDU session information.",
            anchor_terms=["Redundant PDU Session Information"],
            embedding_text="Redundant PDU Session Information",
        ),
    ]
    pipeline = CenteredMultiHopRetrievalPipeline(
        backend=InMemoryMultiHopBackend(records),
        selector=FakeSelector(),
    )

    result = pipeline.run("End to End Redundant Paths", limit=5)

    assert result["entry_specs"][0] == "23501"
    assert result["entry_spec_candidates"]
    assert result["direct_hits"][0]["doc_id"] == "23501:clause:5.33.2.1"
    assert result["selected_anchors"]
    assert result["expansion_specs"]
    assert len(result["selected_anchors"]) == 1
    assert result["merged_clauses"][0]["clause_id"] == "5.33.2.1"


def test_centered_pipeline_supports_llm_only_relevance_mode() -> None:
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
            doc_id="29502:clause:5.2.2.2.1",
            spec_no="29502",
            stage_hint="Stage 3",
            clause_id="5.2.2.2.1",
            clause_title="General",
            text="General text",
            embedding_text="General text",
        ),
    ]
    pipeline = CenteredMultiHopRetrievalPipeline(
        backend=InMemoryMultiHopBackend(records),
        selector=FakeSelector(),
        llm_relevance_only=True,
    )

    result = pipeline.run("End to End Redundant Paths", limit=4)

    assert result["direct_hits"][0]["doc_id"] == "23501:clause:5.33.2.1"


def test_centered_pipeline_judges_hits_per_stage_independently() -> None:
    records = [
        ClauseDoc(
            doc_id="23501:clause:5.33.2.1",
            spec_no="23501",
            stage_hint="Stage 2",
            clause_id="5.33.2.1",
            clause_title="Dual Connectivity based end to end Redundant User Plane Paths",
            text="Stage 2 seed",
            embedding_text="Dual Connectivity based end to end Redundant User Plane Paths",
        ),
        ClauseDoc(
            doc_id="29502:clause:6.1.8",
            spec_no="29502",
            stage_hint="Stage 3",
            clause_id="6.1.8",
            clause_title="Feature Negotiation",
            text="Stage 3 companion",
            embedding_text="Feature Negotiation",
        ),
    ]
    pipeline = CenteredMultiHopRetrievalPipeline(
        backend=InMemoryMultiHopBackend(records),
        selector=FakeSelector(),
        llm_relevance_only=True,
    )

    hits = pipeline._prepare_hits(
        [
            type("Hit", (), {"doc": records[0], "score": 10.0, "matched_text": "a"})(),
            type("Hit", (), {"doc": records[1], "score": 9.0, "matched_text": "b"})(),
        ]
    )
    judged = pipeline._judge_hits_by_stage("test", hits, ["Stage 2", "Stage 3"], stage_limit=1)

    assert {item["doc"].stage_hint for item in judged} == {"Stage 2", "Stage 3"}


def test_infer_entry_specs_uses_judgment_seed_style_queries() -> None:
    records = [
        ClauseDoc(doc_id="a", spec_no="23501", stage_hint="Stage 2", clause_title="System architecture", spec_title="Stage 2 architecture"),
        ClauseDoc(doc_id="b", spec_no="29502", stage_hint="Stage 3", clause_title="Create SM Context service", spec_title="Session Management Services"),
        ClauseDoc(doc_id="c", spec_no="23502", stage_hint="Stage 3", clause_title="N2 Notification procedure", spec_title="Procedures"),
        ClauseDoc(doc_id="d", spec_no="38413", stage_hint="else", clause_title="Functions of NGAP", spec_title="NGAP"),
    ]
    routing_index = build_routing_index(records)

    assert infer_entry_specs(_normalize("Create SM Context service"), routing_index)[:2] == ["23501", "29502"]
    assert "23502" in infer_entry_specs(_normalize("N2 Notification procedure"), routing_index)
    assert "38413" in infer_entry_specs(_normalize("functions of NGAP"), routing_index)


def test_infer_entry_specs_prefers_clause_title_exact_match_spec() -> None:
    records = [
        ClauseDoc(doc_id="a", spec_no="23502", stage_hint="Stage 2", clause_title="UE Triggered Service Request", spec_title="Procedures"),
        ClauseDoc(doc_id="b", spec_no="23501", stage_hint="Stage 2", clause_title="Dual Connectivity based end to end Redundant User Plane Paths", spec_title="Architecture"),
    ]
    routing_index = build_routing_index(records)

    assert infer_entry_specs(_normalize("End to End Redundant Paths"), routing_index)[0] == "23501"


def test_centered_pipeline_reranks_generic_clause_titles_down() -> None:
    records = [
        ClauseDoc(
            doc_id="29502:clause:5.2.2.2.1",
            spec_no="29502",
            stage_hint="Stage 3",
            clause_id="5.2.2.2.1",
            clause_title="General",
            text="Create SM Context Request is described here.",
            anchor_terms=["Create SM Context Request"],
            embedding_text="Create SM Context Request",
        ),
        ClauseDoc(
            doc_id="29502:clause:5.2.2.2.5",
            spec_no="29502",
            stage_hint="Stage 3",
            clause_id="5.2.2.2.5",
            clause_title="Create SM Context service operations",
            text="Create SM Context service procedures are described here.",
            anchor_terms=["Create SM Context service"],
            embedding_text="Create SM Context service",
        ),
    ]
    pipeline = CenteredMultiHopRetrievalPipeline(
        backend=InMemoryMultiHopBackend(records),
        selector=FakeSelector(),
    )

    result = pipeline.run("Create SM Context service", limit=5)

    assert result["merged_clauses"][0]["clause_id"] == "5.2.2.2.5"


def test_stage_filters_are_resolved_from_observed_stage_hints() -> None:
    routing_index = build_routing_index(
        [
            ClauseDoc(doc_id="a", spec_no="99999", stage_hint="else"),
            ClauseDoc(doc_id="b", spec_no="99999", stage_hint="else"),
            ClauseDoc(doc_id="c", spec_no="23501", stage_hint="Stage 2"),
        ]
    )

    assert resolve_spec_stage_filters("99999", ["Stage 2", "Stage 3", "else"], routing_index) == ["else"]
    assert resolve_spec_stage_filters("23501", ["Stage 2"], routing_index) == ["Stage 2"]


def _normalize(query: str):
    from retrieval.query_normalizer import normalize_query

    return normalize_query(query)
