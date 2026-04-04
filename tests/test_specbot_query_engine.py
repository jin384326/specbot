from __future__ import annotations

from pathlib import Path

from app.specbot_query_server import PersistentSpecbotQueryEngine, SpecbotQueryDefaults, SpecbotQueryServerSettings


def make_settings(project_root: Path) -> SpecbotQueryServerSettings:
    return SpecbotQueryServerSettings(
        project_root=project_root,
        defaults=SpecbotQueryDefaults(),
        embed_model="mock-embed",
        openai_model="mock-openai",
        llm_action_provider="mock-provider",
        llm_action_model="mock-llm",
        timeout_seconds=30.0,
        ranking="hybrid",
        schema="spec",
        namespace="spec",
        anchor_boost=1.0,
        title_boost=1.0,
        stage_boost=1.0,
        task_max_concurrency=2,
        task_max_queue_size=4,
        cors_origins=(),
    )


def test_iteration_hits_deduplicates_and_applies_exact_exclusions(tmp_path: Path) -> None:
    hits = PersistentSpecbotQueryEngine.iteration_hits(
        {
            "results": [
                {
                    "spec_no": "23501",
                    "clause_id": "5.1",
                    "parent_clause_id": "5",
                    "clause_path": ["5", "5.1"],
                    "text": "A" * 300,
                    "judgement": {"is_relevant": True},
                },
                {
                    "spec_no": "23501",
                    "clause_id": "5.1",
                    "parent_clause_id": "5",
                    "clause_path": ["5", "5.1"],
                    "text": "duplicate",
                    "judgement": {"is_relevant": True},
                },
                {
                    "spec_no": "23502",
                    "clause_id": "4.2.2.2",
                    "parent_clause_id": "",
                    "clause_path": ["4.2.2.2"],
                    "text": "excluded",
                    "judgement": {"is_relevant": True},
                },
            ]
        },
        exclude_specs=[],
        exclude_clauses=[{"specNo": "23502", "clauseId": "4.2.2.2"}],
    )

    assert hits == [
        {
            "specNo": "23501",
            "clauseId": "5.1",
            "parentClauseId": "5",
            "clausePath": ["5", "5.1"],
            "textPreview": "A" * 240,
        }
    ]


def test_engine_resolves_scoped_registry_candidates(monkeypatch, tmp_path: Path) -> None:
    class StubJudge:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

    monkeypatch.setattr("app.specbot_query_engine.ChatOpenAIRelevanceJudge", StubJudge)
    settings = make_settings(tmp_path)
    engine = PersistentSpecbotQueryEngine(settings)
    scoped_registry = tmp_path / "artifacts" / "spec_query_registries" / "2025-12" / "Rel-18" / "spec_query_registry.json"
    scoped_registry.parent.mkdir(parents=True, exist_ok=True)
    scoped_registry.write_text("{}", encoding="utf-8")

    resolved = engine._resolve_scoped_registry(
        registry_path=str(tmp_path / "artifacts" / "spec_query_registry.json"),
        release_data="2025-12",
        release="Rel-18",
    )

    assert resolved == scoped_registry
