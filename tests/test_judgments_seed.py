from __future__ import annotations

import json
from pathlib import Path

from retrieval.query_normalizer import normalize_query
from retrieval.vespa_adapter import build_vespa_query


def load_judgments() -> list[dict]:
    path = Path("/home/jin3843/codex_project/eval/judgments_seed.jsonl")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_judgment_seed_queries_build_normalized_query_and_yql() -> None:
    judgments = load_judgments()
    assert judgments
    for row in judgments:
        normalized = normalize_query(row["query"])
        request = build_vespa_query(normalized, hits=5)
        assert normalized.normalized_query
        assert request.yql.startswith("select * from sources * where ")


def test_judgment_seed_contains_key_phrase_query_cases() -> None:
    judgment_queries = {row["query"] for row in load_judgments()}
    assert "Create SM Context service" in judgment_queries
    assert "N2 Notification procedure" in judgment_queries
    assert "UE IP Address Allocation" in judgment_queries
