from __future__ import annotations

from pathlib import Path

from app.specbot_query_server import SpecbotQueryDefaults, SpecbotQueryServerSettings, create_app


def test_query_server_uses_clause_summary_prompts_for_llm_actions(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    class StubEngine:
        def __init__(self, settings) -> None:
            captured["engine_settings"] = settings

    class StubLLMActionService:
        def __init__(self, **kwargs) -> None:
            captured["llm_kwargs"] = kwargs

        def available_actions(self):
            return [{"type": "translate", "label": "Translate"}]

    class StubLimiter:
        def __init__(self, **kwargs) -> None:
            captured["limiter_kwargs"] = kwargs

    class StubBackend:
        pass

    monkeypatch.setattr("app.specbot_query_server.PersistentSpecbotQueryEngine", StubEngine)
    monkeypatch.setattr("app.specbot_query_server.LLMActionService", StubLLMActionService)
    monkeypatch.setattr("app.specbot_query_server.SharedTaskLimiter", StubLimiter)
    monkeypatch.setattr("app.specbot_query_server.VespaEndpoint", StubBackend)

    settings = SpecbotQueryServerSettings(
        project_root=tmp_path,
        defaults=SpecbotQueryDefaults(),
        embed_model="mock-embed",
        openai_model="mock-openai",
        llm_action_provider="mock",
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

    app = create_app(settings)

    assert app.title == "SpecBot Query API"
    assert captured["llm_kwargs"]["system_prompt_path"] == tmp_path / "system_prompt_clause_summary.txt"
    assert captured["llm_kwargs"]["user_prompt_path"] == tmp_path / "user_prompt_clause_summary.txt"
