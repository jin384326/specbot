from __future__ import annotations

import json
from pathlib import Path

from retrieval.pipeline import InMemoryBackend, RetrievalPipeline
from retrieval.query_normalizer import QueryFeatureRegistry, build_query_feature_registry_from_corpus, normalize_query
from retrieval.anchor_selector import select_anchors
from retrieval.vespa_adapter import build_vespa_query
from parser.models import ClauseDoc, TableRowDoc


def test_query_normalizer_uses_registry_and_filters_stopwords() -> None:
    registry = QueryFeatureRegistry(
        aliases={"SSC": ["session and service continuity"]},
        canonical_terms={"PDU Session": ["session management"]},
    )
    normalized = normalize_query("How does SSC work for PDU Session in TS 23.501?", registry=registry)
    compound = normalize_query("N1N2 message transfer")

    assert "SSC" in normalized.aliases
    assert "session and service continuity" in normalized.aliases
    assert "23501" in normalized.hinted_specs
    assert "Stage 2" in normalize_query("stage 2 behavior").hinted_stages
    assert "PDU Session" in normalized.candidate_anchors
    assert "How" not in normalized.features["tokens"]
    assert "N1N2MessageTransfer" in compound.aliases


def test_query_registry_infers_specs_from_corpus_terms(tmp_path: Path) -> None:
    records = [
        ClauseDoc(
            doc_id="23501:clause:4.2",
            spec_no="23501",
            clause_id="4.2",
            clause_title="Architecture overview",
            text="Architecture principles for the 5G System.",
            anchor_terms=["architecture overview"],
            keywords=["architecture", "overview"],
        ),
        ClauseDoc(
            doc_id="23502:clause:4.3.2",
            spec_no="23502",
            clause_id="4.3.2",
            clause_title="PDU Session establishment procedure",
            text="Registration and service request procedures are described here.",
            anchor_terms=["PDU Session establishment", "registration procedure"],
            keywords=["registration", "procedure", "pdu", "session"],
        ),
        TableRowDoc(
            doc_id="23502:table:1:row:1",
            spec_no="23502",
            clause_id="4.3.2",
            clause_title="General",
            table_title="General",
            row_header="N1N2 message transfer",
            text="N1N2 message transfer procedure",
            anchor_terms=["N1N2 message transfer"],
            keywords=["n1n2", "message", "transfer"],
        ),
    ]
    corpus_path = tmp_path / "corpus.jsonl"
    with corpus_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record.to_dict(), ensure_ascii=True) + "\n")

    registry = build_query_feature_registry_from_corpus(corpus_path)
    normalized = normalize_query("where is PDU Session Establishment procedure defined", registry=registry)

    assert "23502" in normalized.inferred_specs
    assert any("pdu session establishment procedure" in term for term in registry.spec_term_hints["23502"])


def test_query_registry_matches_compound_suffix_variants() -> None:
    registry = QueryFeatureRegistry(spec_term_hints={"23502": {"n1 n2 message transfer": 2.5}})
    normalized = normalize_query("N1N2 message transfer", registry=registry)
    assert normalized.inferred_specs == ["23502"]


def test_stage_filter_normalization_supports_else() -> None:
    normalized = normalize_query("generic query", stage_filters=["else"])
    assert normalized.stage_filters == ["else"]


def test_query_normalizer_preserves_long_phrase_for_clause_like_query() -> None:
    normalized = normalize_query("End to End Redundant Paths")
    assert "End to End Redundant Paths" in normalized.candidate_anchors
    assert "End" not in normalized.features["tokens"]
    assert "Paths" not in normalized.features["tokens"]


def test_anchor_selector_penalizes_generic_and_noisy_candidates() -> None:
    ranked = select_anchors(
        [
            {"anchor": "RAN", "sources": ["acronym"], "doc_count": 10, "spec_count": 1},
            {"anchor": "37340", "sources": ["spec_reference"], "doc_count": 7, "spec_count": 1},
            {
                "anchor": "Dual Connectivity based end to end Redundant User Plane Paths",
                "sources": ["clause_title"],
                "doc_count": 10,
                "spec_count": 1,
            },
        ],
        limit=5,
    )
    assert ranked[0]["anchor"] == "Dual Connectivity based end to end Redundant User Plane Paths"
    assert all(item["anchor"] != "RAN" for item in ranked)


def test_pipeline_expanded_search_prefers_non_reject_signals() -> None:
    records = [
        ClauseDoc(
            doc_id="23501:clause:4.3.2",
            spec_no="23501",
            clause_id="4.3.2",
            clause_title="SSC mode handling",
            text="Session and Service Continuity (SSC) is handled by the SMF for PDU Session procedures.",
            anchor_terms=["SSC mode", "SMF"],
            keywords=["session", "continuity", "smf"],
            embedding_text="SSC mode handling Session and Service Continuity SMF PDU Session",
        ),
        TableRowDoc(
            doc_id="23502:table:1:row:1",
            spec_no="23502",
            clause_id="6.3.2",
            clause_title="PDU session procedures",
            row_header="SSC mode",
            row_cells=["SSC mode", "1"],
            text="SSC mode: 1",
            anchor_terms=["SSC mode"],
            keywords=["ssc", "mode"],
            embedding_text="SSC mode row",
        ),
    ]
    pipeline = RetrievalPipeline(InMemoryBackend(records))
    result = pipeline.run("SSC mode for PDU Session", limit=5)

    assert result["ranked_specs"][0]["spec_no"] in {"23501", "23502"}
    assert any(signal["classification"] != "reject" for signal in result["signals"])


def test_build_vespa_query_preview() -> None:
    normalized = normalize_query("SSC mode in TS 23.501", stage_filters=["stage2"])
    request = build_vespa_query(normalized, hits=7)

    assert request.hits == 7
    assert "spec_no contains \"23501\"" in request.yql
    assert "embedding_text contains \"23.501\"" in request.yql
    assert " and (spec_no contains \"23501\")" in request.yql
    assert " and (stage_hint contains \"Stage 2\")" in request.yql
    assert "stage_hint contains \"Stage 2\"" in build_vespa_query(normalize_query("Stage 2 in TS 23.501")).yql


def test_rank_specs_does_not_overreward_many_weaker_hits() -> None:
    hits = [
        {
            "doc_id": "23501:a",
            "spec_no": "23501",
            "score": 2.0,
            "reason_type": "direct_hit",
            "matched_text": "ssc",
            "explanation": "direct_hit matched ssc",
        },
        {
            "doc_id": "23501:b",
            "spec_no": "23501",
            "score": 1.9,
            "reason_type": "direct_hit",
            "matched_text": "mode",
            "explanation": "direct_hit matched mode",
        },
        {
            "doc_id": "23501:c",
            "spec_no": "23501",
            "score": 1.8,
            "reason_type": "direct_hit",
            "matched_text": "session",
            "explanation": "direct_hit matched session",
        },
        {
            "doc_id": "23502:a",
            "spec_no": "23502",
            "score": 3.2,
            "reason_type": "direct_hit",
            "matched_text": "ssc mode",
            "explanation": "direct_hit matched ssc mode",
        },
        {
            "doc_id": "23502:b",
            "spec_no": "23502",
            "score": 2.4,
            "reason_type": "table_row_hit",
            "matched_text": "pdu session",
            "explanation": "table_row_hit matched pdu session",
        },
    ]

    pipeline = RetrievalPipeline(InMemoryBackend([]))
    ranked_specs = pipeline.rank_specs(hits)

    assert ranked_specs[0]["spec_no"] == "23502"
