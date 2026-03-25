from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.clause_browser.services import SpecbotQueryDefaults
from embedding.config import DEFAULT_EMBEDDING_DEVICE, DEFAULT_EMBEDDING_MODEL
from embedding.registry import create_embedding_provider
from retrieval.iterative_llm_retriever import ChatOpenAIRelevanceJudge, IterativeLLMRetriever
from retrieval.query_normalizer import QueryFeatureRegistry
from retrieval.vespa_multi_hop_backend import VespaMultiHopBackend
from vespa.http_adapter import VespaEndpoint


class SpecbotSettingsPayload(BaseModel):
    baseUrl: str = Field(min_length=1, max_length=200)
    configBaseUrl: str = Field(default="", max_length=200)
    limit: int = Field(default=4, ge=1, le=20)
    iterations: int = Field(default=2, ge=1, le=10)
    nextIterationLimit: int = Field(default=2, ge=1, le=20)
    summary: str = Field(default="short", min_length=1, max_length=50)
    registry: str = Field(min_length=1, max_length=500)
    localModelDir: str = Field(min_length=1, max_length=500)
    device: str = Field(default="cuda", min_length=1, max_length=50)
    sparseBoost: float = Field(default=0.0, ge=0.0, le=10.0)
    vectorBoost: float = Field(default=1.0, ge=0.0, le=10.0)


class SpecbotQueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    settings: SpecbotSettingsPayload | None = None


@dataclass(frozen=True)
class SpecbotQueryServerSettings:
    project_root: Path
    defaults: SpecbotQueryDefaults
    embed_model: str
    openai_model: str
    timeout_seconds: float
    ranking: str
    schema: str
    namespace: str
    anchor_boost: float
    title_boost: float
    stage_boost: float


class PersistentSpecbotQueryEngine:
    def __init__(self, settings: SpecbotQueryServerSettings) -> None:
        self._settings = settings
        self._judge = ChatOpenAIRelevanceJudge(
            model=settings.openai_model,
            timeout=int(settings.timeout_seconds),
            extraction_mode="keyword",
        )
        self._registry_cache: dict[str, QueryFeatureRegistry] = {}
        self._embedding_cache: dict[tuple[str, str, str], Any] = {}

    @property
    def defaults(self) -> SpecbotQueryDefaults:
        return self._settings.defaults

    def run(self, query: str, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
        effective = self._merge_settings(overrides or {})
        registry = self._get_registry(str(effective["registry"]))
        embedding_provider = self._get_embedding_provider(
            local_model_dir=str(effective["localModelDir"]),
            device=str(effective["device"]),
        )
        endpoint = VespaEndpoint(
            base_url=str(effective["baseUrl"]),
            schema=self._settings.schema,
            namespace=self._settings.namespace,
            config_base_url=str(effective["configBaseUrl"]) or None,
        )
        backend = VespaMultiHopBackend(
            endpoint=endpoint,
            registry=registry,
            embedding_provider=embedding_provider,
            ranking=self._settings.ranking,
            summary=str(effective["summary"]),
            sparse_boost=float(effective["sparseBoost"]),
            vector_boost=float(effective["vectorBoost"]),
            anchor_boost=self._settings.anchor_boost,
            title_boost=self._settings.title_boost,
            stage_boost=self._settings.stage_boost,
            timeout=self._settings.timeout_seconds,
            max_retries=1,
            retry_backoff_seconds=0.5,
        )
        retriever = IterativeLLMRetriever(backend=backend, evaluator=self._judge)
        result = retriever.run(
            query,
            limit=int(effective["limit"]),
            iterations=int(effective["iterations"]),
            next_iteration_limit=int(effective["nextIterationLimit"]),
        )
        return {
            "query": query,
            "settings": effective,
            "hits": self._extract_hits(result),
            "rawResult": result,
        }

    def _merge_settings(self, overrides: dict[str, Any]) -> dict[str, Any]:
        defaults = self._settings.defaults.to_dict()
        merged = {**defaults, **{key: value for key, value in overrides.items() if value is not None}}
        merged["registry"] = str(self._resolve_path(str(merged["registry"])))
        merged["localModelDir"] = str(self._resolve_path(str(merged["localModelDir"])))
        return merged

    def _resolve_path(self, value: str) -> Path:
        path = Path(value)
        if path.is_absolute():
            return path
        return self._settings.project_root / path

    def _get_registry(self, registry_path: str) -> QueryFeatureRegistry:
        cached = self._registry_cache.get(registry_path)
        if cached is not None:
            return cached
        registry = QueryFeatureRegistry.from_json(registry_path)
        self._registry_cache[registry_path] = registry
        return registry

    def _get_embedding_provider(self, *, local_model_dir: str, device: str):
        cache_key = (self._settings.embed_model, local_model_dir, device)
        cached = self._embedding_cache.get(cache_key)
        if cached is not None:
            return cached
        provider = create_embedding_provider(
            self._settings.embed_model,
            local_dir=local_model_dir,
            device=device or DEFAULT_EMBEDDING_DEVICE,
            load_in_4bit=True,
            max_length=2048,
        )
        self._embedding_cache[cache_key] = provider
        return provider

    @staticmethod
    def _extract_hits(payload: dict[str, Any]) -> list[dict[str, Any]]:
        hits: list[dict[str, Any]] = []
        for item in payload.get("relevant_documents", []) or []:
            texts = item.get("texts") or []
            hits.append(
                {
                    "specNo": str(item.get("spec_no", "")),
                    "clauseId": str(item.get("clause_id", "")),
                    "parentClauseId": str(item.get("parent_clause_id", "")),
                    "clausePath": [str(part) for part in item.get("clause_path", [])],
                    "textPreview": texts[0][:240] if texts else "",
                }
            )
        return hits


def create_app(settings: SpecbotQueryServerSettings | None = None) -> FastAPI:
    active_settings = settings or load_settings()
    engine = PersistentSpecbotQueryEngine(active_settings)
    app = FastAPI(title="SpecBot Query API", version="0.1.0")

    @app.get("/health", include_in_schema=False)
    def health() -> dict[str, object]:
        return {"ok": True, "baseUrl": active_settings.defaults.base_url}

    @app.get("/config")
    def config() -> dict[str, object]:
        return {"defaults": engine.defaults.to_dict()}

    @app.post("/query")
    def query(request: SpecbotQueryRequest) -> dict[str, object]:
        try:
            return engine.run(
                query=request.query.strip(),
                overrides=request.settings.model_dump(mode="json") if request.settings else None,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    return app


def load_settings() -> SpecbotQueryServerSettings:
    project_root = Path(__file__).resolve().parents[1]
    defaults = SpecbotQueryDefaults(
        base_url=os.environ.get("SPECBOT_QUERY_BASE_URL", "http://localhost:8080").strip() or "http://localhost:8080",
        config_base_url=os.environ.get("SPECBOT_QUERY_CONFIG_BASE_URL", "http://localhost:19071").strip() or "http://localhost:19071",
        limit=int(os.environ.get("SPECBOT_QUERY_LIMIT", "4")),
        iterations=int(os.environ.get("SPECBOT_QUERY_ITERATIONS", "2")),
        next_iteration_limit=int(os.environ.get("SPECBOT_QUERY_NEXT_ITERATION_LIMIT", "2")),
        summary=os.environ.get("SPECBOT_QUERY_SUMMARY", "short").strip() or "short",
        registry=os.environ.get("SPECBOT_QUERY_REGISTRY", "./artifacts/spec_query_registry.json").strip() or "./artifacts/spec_query_registry.json",
        local_model_dir=os.environ.get("SPECBOT_QUERY_LOCAL_MODEL_DIR", "models/Qwen3-Embedding-0.6B").strip() or "models/Qwen3-Embedding-0.6B",
        device=os.environ.get("SPECBOT_QUERY_DEVICE", DEFAULT_EMBEDDING_DEVICE).strip() or DEFAULT_EMBEDDING_DEVICE,
        sparse_boost=float(os.environ.get("SPECBOT_QUERY_SPARSE_BOOST", "0")),
        vector_boost=float(os.environ.get("SPECBOT_QUERY_VECTOR_BOOST", "1")),
    )
    return SpecbotQueryServerSettings(
        project_root=project_root,
        defaults=defaults,
        embed_model=os.environ.get("SPECBOT_QUERY_EMBED_MODEL", DEFAULT_EMBEDDING_MODEL).strip() or DEFAULT_EMBEDDING_MODEL,
        openai_model=os.environ.get("SPECBOT_QUERY_OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini",
        timeout_seconds=float(os.environ.get("SPECBOT_QUERY_TIMEOUT", "30")),
        ranking=os.environ.get("SPECBOT_QUERY_RANKING", "hybrid").strip() or "hybrid",
        schema=os.environ.get("SPECBOT_QUERY_SCHEMA", "spec_finder").strip() or "spec_finder",
        namespace=os.environ.get("SPECBOT_QUERY_NAMESPACE", "spec_finder").strip() or "spec_finder",
        anchor_boost=float(os.environ.get("SPECBOT_QUERY_ANCHOR_BOOST", "1.15")),
        title_boost=float(os.environ.get("SPECBOT_QUERY_TITLE_BOOST", "1.2")),
        stage_boost=float(os.environ.get("SPECBOT_QUERY_STAGE_BOOST", "1.1")),
    )
