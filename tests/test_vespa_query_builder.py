from __future__ import annotations

from retrieval.query_normalizer import QueryFeatureRegistry, normalize_query
from retrieval.vespa_adapter import build_vespa_query


def test_vespa_query_builder_uses_soft_metadata_hints() -> None:
    normalized = normalize_query("SSC mode in TS 23.501 stage 2")
    request = build_vespa_query(normalized, hits=5)
    assert "spec_no contains \"23501\"" in request.yql
    assert "embedding_text contains \"23.501\"" in request.yql
    assert "stage_hint contains \"Stage 2\"" in request.yql
    assert " and (spec_no contains \"23501\")" in request.yql


def test_vespa_query_builder_uses_inferred_spec_hint_when_query_is_procedural() -> None:
    registry = QueryFeatureRegistry(spec_term_hints={"23502": {"pdu session establishment procedure": 2.6}})
    normalized = normalize_query("where is PDU Session Establishment procedure defined", registry=registry)
    request = build_vespa_query(normalized, hits=5)
    assert normalized.inferred_specs == ["23502"]
    assert "spec_no contains \"23502\"" in request.yql
    assert "embedding_text contains \"23.502\"" in request.yql
    assert " and (spec_no contains \"23502\")" not in request.yql


def test_vespa_query_builder_adds_nearest_neighbor_when_vector_present() -> None:
    normalized = normalize_query("SSC mode", query_vector=[0.1] * 16)
    request = build_vespa_query(normalized, hits=5)
    assert "nearestNeighbor(dense_embedding, query_embedding)" in request.yql
    assert "input.query(query_embedding)" in request.to_params()


def test_vespa_query_builder_searches_aliases_in_text_fields() -> None:
    normalized = normalize_query("N1N2 message transfer")
    request = build_vespa_query(normalized, hits=5)
    assert "text contains \"N1N2MessageTransfer\"" in request.yql
    assert "embedding_text contains \"N1N2MessageTransfer\"" in request.yql


def test_vespa_query_builder_serializes_vector_dimension_from_query() -> None:
    normalized = normalize_query("SSC mode", query_vector=[0.1] * 1024)
    request = build_vespa_query(normalized, hits=5)
    assert "tensor<float>(x[1024])" in request.to_params()["input.query(query_embedding)"]


def test_vespa_query_builder_keeps_long_phrase_for_title_fields() -> None:
    normalized = normalize_query("End to End Redundant Paths")
    request = build_vespa_query(normalized, hits=5)
    assert 'clause_title contains "End to End Redundant Paths"' in request.yql
    assert 'entity_name contains "End to End Redundant Paths"' in request.yql
