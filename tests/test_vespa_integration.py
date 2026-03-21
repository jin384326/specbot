from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from urllib import error
from unittest.mock import patch

from parser.models import ClauseDoc
from retrieval.vespa_multi_hop_backend import VespaMultiHopBackend, doc_record_from_vespa_hit
from retrieval.query_normalizer import QueryFeatureRegistry
from vespa.export_for_vespa import doc_record_to_vespa_feed, export_corpus_to_vespa_feed
from vespa.http_adapter import (
    VespaEndpoint,
    build_application_package_bytes,
    deploy_application_package,
    feed_documents,
    query_vespa,
    smoke_test_vespa,
    wait_for_vespa,
)


def test_export_includes_stage_hint_and_release_data(tmp_path: Path) -> None:
    record = ClauseDoc(
        doc_id="23501:clause:1",
        spec_no="23501",
        spec_title="System architecture for the 5G System (5GS); Stage 2 (Release 18)",
        release="Rel-18",
        release_data="2025-12",
        stage_hint="Stage 2",
        clause_id="1",
        clause_title="Scope",
        text="Scope text",
    )
    feed_doc = doc_record_to_vespa_feed(record)
    assert feed_doc["fields"]["stage_hint"] == "Stage 2"
    assert feed_doc["fields"]["release_data"] == "2025-12"
    assert feed_doc["fields"]["table_raw_json"] == "[]"

    input_path = tmp_path / "input.jsonl"
    input_path.write_text(json.dumps(record.to_dict()) + "\n", encoding="utf-8")
    output_path = tmp_path / "feed.jsonl"
    count = export_corpus_to_vespa_feed(input_path, output_path)
    assert count == 1
    assert output_path.exists()


def test_export_preserves_else_stage_hint() -> None:
    record = ClauseDoc(
        doc_id="29999:clause:1",
        spec_no="29999",
        spec_title="Unknown spec",
        stage_hint="else",
        clause_id="1",
        clause_title="Scope",
        text="Scope text",
    )
    feed_doc = doc_record_to_vespa_feed(record)
    assert feed_doc["fields"]["stage_hint"] == "else"


def test_http_adapter_builds_expected_requests() -> None:
    endpoint = VespaEndpoint(base_url="http://localhost:8080")
    payload = {"put": "id:spec_finder:doc::23501:clause:1", "fields": {"doc_id": "23501:clause:1"}}

    with patch("vespa.http_adapter._http_json", return_value={"id": "ok"}) as mock_http:
        result = feed_documents(endpoint, [payload])
        assert result.succeeded == 1
        assert result.failed == 0
        mock_http.assert_called_once()
        assert "/document/v1/spec_finder/spec_finder/docid/" in mock_http.call_args.kwargs["url"]

    with patch("vespa.http_adapter._http_json", return_value={"root": {"children": []}}) as mock_http:
        result = query_vespa(endpoint, {"yql": "select * from sources * where true"})
        assert "root" in result
        called_url = mock_http.call_args.kwargs["url"]
        assert called_url.startswith("http://localhost:8080/search/?")


def test_http_adapter_retries_and_records_failure() -> None:
    endpoint = VespaEndpoint(base_url="http://localhost:8080")
    payload = {"put": "id:spec_finder:doc::23501:clause:1", "fields": {"doc_id": "23501:clause:1"}}
    transient = error.URLError("temporary")

    with patch("vespa.http_adapter._http_json", side_effect=[transient, {"id": "ok"}]) as mock_http:
        result = feed_documents(endpoint, [payload], max_retries=1, retry_backoff_seconds=0.0)
        assert result.succeeded == 1
        assert result.attempts[0].attempts == 2
        assert mock_http.call_count == 2


def test_http_adapter_can_feed_documents_concurrently() -> None:
    endpoint = VespaEndpoint(base_url="http://localhost:8080")
    payloads = [
        {"put": f"id:spec_finder:doc::{idx}", "fields": {"doc_id": str(idx)}}
        for idx in range(4)
    ]
    lock = threading.Lock()
    active = 0
    max_active = 0

    def fake_http_json(**kwargs):
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.05)
        with lock:
            active -= 1
        return {"id": kwargs["url"]}

    with patch("vespa.http_adapter._http_json", side_effect=fake_http_json):
        result = feed_documents(endpoint, payloads, max_workers=4)

    assert result.succeeded == 4
    assert result.failed == 0
    assert max_active >= 2


def test_package_build_and_deploy_request(tmp_path: Path) -> None:
    app_dir = tmp_path / "vespa-app"
    app_dir.mkdir()
    (app_dir / "services.xml").write_text("<services/>", encoding="utf-8")
    (app_dir / "schemas").mkdir()
    (app_dir / "schemas" / "spec_finder.sd").write_text("schema spec_finder {}", encoding="utf-8")

    payload = build_application_package_bytes(app_dir)
    assert len(payload) > 0

    endpoint = VespaEndpoint(base_url="http://localhost:8080", config_base_url="http://localhost:19071")
    with patch("vespa.http_adapter._http_json", return_value={"session-id": "1"}) as mock_http:
        result = deploy_application_package(endpoint, app_dir, timeout=1.0)
        assert result["session-id"] == "1"
        assert mock_http.call_args.kwargs["headers"]["Content-Type"] == "application/zip"
        assert mock_http.call_args.kwargs["url"].startswith("http://localhost:19071/application/v2/tenant/default/")


def test_smoke_test_summarizes_live_response() -> None:
    endpoint = VespaEndpoint(base_url="http://localhost:8080")
    response = {
        "root": {
            "fields": {"totalCount": 2},
            "children": [{"id": "id:spec_finder:doc::1"}, {"id": "id:spec_finder:doc::2"}],
        }
    }
    with patch("vespa.http_adapter.query_vespa", return_value=response):
        result = smoke_test_vespa(endpoint, {"yql": "select * from sources * where true"})
        assert result["total_hit_count"] == 2
        assert result["returned_hits"] == 2


def test_wait_for_vespa_returns_ready_after_retry() -> None:
    endpoint = VespaEndpoint(base_url="http://localhost:8080")
    with patch("vespa.http_adapter.query_vespa", side_effect=[RuntimeError("booting"), {"root": {}}]) as mock_query:
        result = wait_for_vespa(endpoint, timeout_seconds=1.0, poll_interval_seconds=0.0)
        assert result["ready"] is True
        assert result["attempts"] == 2
        assert mock_query.call_count == 2


def test_wait_for_vespa_can_report_timeout() -> None:
    endpoint = VespaEndpoint(base_url="http://localhost:8080")
    with patch("vespa.http_adapter.query_vespa", side_effect=RuntimeError("still booting")):
        result = wait_for_vespa(endpoint, timeout_seconds=0.01, poll_interval_seconds=0.0)
        assert result["ready"] is False
        assert "still booting" in result["error"]


def test_doc_record_from_vespa_hit_restores_record_shape() -> None:
    hit = {
        "fields": {
            "doc_id": "23501:clause:1",
            "doc_type": "clause_doc",
            "spec_no": "23501",
            "stage_hint": "Stage 2",
            "clause_id": "1",
            "clause_title": "Scope",
            "text": "Scope text",
            "table_raw_json": "[]",
        }
    }
    record = doc_record_from_vespa_hit(hit)
    assert record.doc_id == "23501:clause:1"
    assert record.content_kind == "clause"


def test_vespa_multi_hop_backend_fans_out_by_stage_filter() -> None:
    endpoint = VespaEndpoint(base_url="http://localhost:8080")
    backend = VespaMultiHopBackend(endpoint=endpoint, registry=QueryFeatureRegistry())
    response = {
        "root": {
            "children": [
                {
                    "relevance": 3.2,
                    "fields": {
                        "doc_id": "23501:clause:1",
                        "doc_type": "clause_doc",
                        "spec_no": "23501",
                        "stage_hint": "Stage 2",
                        "clause_id": "1",
                        "clause_title": "Scope",
                        "text": "Scope text",
                        "table_raw_json": "[]",
                    },
                }
            ]
        }
    }
    with patch("retrieval.vespa_multi_hop_backend.query_vespa", return_value=response) as mock_query:
        hits = backend.search(["Scope"], limit=5, stage_filters=["Stage 2", "Stage 3"], spec_filters=["23501"])
        assert len(hits) == 1
        assert hits[0].doc.spec_no == "23501"
        assert mock_query.call_count == 2
