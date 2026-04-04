from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.clause_browser.services import SpecbotQueryDefaults
from embedding.config import DEFAULT_EMBEDDING_DEVICE
from embedding.registry import create_embedding_provider
from retrieval.iterative_llm_retriever import ChatOpenAIRelevanceJudge, IterativeLLMRetriever
from retrieval.query_normalizer import QueryFeatureRegistry
from retrieval.vespa_multi_hop_backend import VespaMultiHopBackend
from vespa.http_adapter import VespaEndpoint


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SpecbotQueryServerSettings:
    project_root: Path
    defaults: SpecbotQueryDefaults
    embed_model: str
    openai_model: str
    llm_action_provider: str
    llm_action_model: str
    timeout_seconds: float
    ranking: str
    schema: str
    namespace: str
    anchor_boost: float
    title_boost: float
    stage_boost: float
    task_max_concurrency: int
    task_max_queue_size: int
    cors_origins: tuple[str, ...]


class PersistentSpecbotQueryEngine:
    def __init__(self, settings: SpecbotQueryServerSettings) -> None:
        self._settings = settings
        self._judge = ChatOpenAIRelevanceJudge(
            model=settings.openai_model,
            timeout=int(settings.timeout_seconds),
            extraction_mode="sentence-summary",
        )
        self._registry_cache: dict[str, QueryFeatureRegistry] = {}
        self._embedding_cache: dict[tuple[str, str, str], Any] = {}

    @property
    def defaults(self) -> SpecbotQueryDefaults:
        return self._settings.defaults

    def run(
        self,
        query: str,
        overrides: dict[str, Any] | None = None,
        exclude_specs: list[str] | None = None,
        exclude_clauses: list[dict[str, Any]] | None = None,
        release_data: str | None = None,
        release: str | None = None,
        should_cancel=None,
        on_iteration_complete=None,
        on_relevant_result=None,
    ) -> dict[str, Any]:
        effective = self._merge_settings(overrides or {})
        requested_iterations = max(0, int(effective["iterations"]))
        total_iterations = requested_iterations + 1
        logger.info(
            "SpecBot query run start query=%r iterations=%s total_iterations=%s next_iteration_limit=%s followup_mode=%s summary=%s query_depth=%s release_data=%s release=%s exclude_specs=%d exclude_clauses=%d",
            query,
            requested_iterations,
            total_iterations,
            effective.get("nextIterationLimit"),
            effective.get("followupMode"),
            effective.get("summary"),
            effective.get("queryDepth"),
            release_data or "",
            release or "",
            len(exclude_specs or []),
            len(exclude_clauses or []),
        )
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
        self._judge.extraction_mode = str(effective.get("followupMode") or "sentence-summary")
        scoped_registry = self._resolve_scoped_registry(
            registry_path=str(effective["registry"]),
            release_data=release_data,
            release=release,
        )
        if scoped_registry is not None:
            registry = self._get_registry(str(scoped_registry))
            backend.registry = registry
            logger.info("SpecBot query using scoped registry path=%s", scoped_registry)
        else:
            logger.info("SpecBot query using global registry path=%s", effective["registry"])
        result = retriever.run(
            query,
            limit=int(effective["limit"]),
            iterations=total_iterations,
            next_iteration_limit=int(effective["nextIterationLimit"]),
            release_filters=[release] if release else None,
            release_data_filters=[release_data] if release_data else None,
            exclude_specs=[str(item).strip() for item in (exclude_specs or []) if str(item).strip()],
            exclude_clause_pairs=[
                (
                    str(item.get("specNo") or item.get("spec_no") or "").strip(),
                    str(item.get("clauseId") or item.get("clause_id") or "").strip(),
                )
                for item in (exclude_clauses or [])
                if str(item.get("specNo") or item.get("spec_no") or "").strip()
                and str(item.get("clauseId") or item.get("clause_id") or "").strip()
            ],
            should_cancel=should_cancel,
            on_iteration_complete=on_iteration_complete,
            on_relevant_result=on_relevant_result,
        )
        filtered_hits = self._apply_exclusions(
            self._extract_hits(result),
            exclude_specs=exclude_specs or [],
            exclude_clauses=exclude_clauses or [],
        )
        logger.info(
            "SpecBot query run complete query=%r relevant_documents=%d filtered_hits=%d",
            query,
            len(result.get("relevant_documents", []) or []),
            len(filtered_hits),
        )
        return {
            "query": query,
            "settings": effective,
            "hits": filtered_hits,
            "rawResult": result,
        }

    @staticmethod
    def iteration_hits(
        payload: dict[str, Any],
        *,
        exclude_specs: list[str] | None = None,
        exclude_clauses: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        hits: list[dict[str, Any]] = []
        seen_pairs: set[tuple[str, str]] = set()
        excluded_specs = {str(item).strip() for item in (exclude_specs or []) if str(item).strip()}
        excluded_clause_pairs = {
            (str(item.get("specNo") or item.get("spec_no") or "").strip(), str(item.get("clauseId") or item.get("clause_id") or "").strip())
            for item in (exclude_clauses or [])
            if str(item.get("specNo") or item.get("spec_no") or "").strip()
            and str(item.get("clauseId") or item.get("clause_id") or "").strip()
        }
        for item in payload.get("results", []) or []:
            judgement = item.get("judgement") or {}
            if not judgement.get("is_relevant"):
                continue
            spec_no = str(item.get("spec_no") or "").strip()
            clause_id = str(item.get("clause_id") or "").strip()
            if not spec_no or not clause_id:
                continue
            if spec_no in excluded_specs or (spec_no, clause_id) in excluded_clause_pairs:
                continue
            pair = (spec_no, clause_id)
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            text = str(item.get("text") or "").strip()
            hits.append(
                {
                    "specNo": spec_no,
                    "clauseId": clause_id,
                    "parentClauseId": str(item.get("parent_clause_id") or "").strip(),
                    "clausePath": [str(part) for part in item.get("clause_path") or []],
                    "textPreview": text[:240],
                }
            )
        return hits

    def _merge_settings(self, overrides: dict[str, Any]) -> dict[str, Any]:
        defaults = self._settings.defaults.to_dict()
        merged = {**defaults, **{key: value for key, value in overrides.items() if value is not None}}
        merged["registry"] = str(self._resolve_path(str(merged["registry"])))
        merged["localModelDir"] = str(self._resolve_path(str(merged["localModelDir"])))
        return merged

    def _resolve_scoped_registry(self, *, registry_path: str, release_data: str | None, release: str | None) -> Path | None:
        if not release_data or not release:
            return None
        registry_file = Path(registry_path)
        candidates: list[Path] = [
            self._settings.project_root / "artifacts" / "spec_query_registries" / release_data / release / "spec_query_registry.json",
            registry_file.parent / "spec_query_registries" / release_data / release / "spec_query_registry.json",
            registry_file.parent.parent / release_data / release / "spec_query_registry.json",
        ]
        for candidate in candidates:
            if candidate.is_file():
                return candidate
        logger.info(
            "SpecBot query scoped registry not found release_data=%s release=%s registry_path=%s tried=%s",
            release_data,
            release,
            registry_path,
            [str(path) for path in candidates],
        )
        return None

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

    @staticmethod
    def _apply_exclusions(
        hits: list[dict[str, Any]],
        *,
        exclude_specs: list[str],
        exclude_clauses: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        excluded_specs = {str(item).strip() for item in exclude_specs if str(item).strip()}
        excluded_clause_pairs = {
            (str(item.get("specNo") or "").strip(), str(item.get("clauseId") or "").strip())
            for item in exclude_clauses
            if str(item.get("specNo") or "").strip() and str(item.get("clauseId") or "").strip()
        }
        return [
            hit
            for hit in hits
            if str(hit.get("clauseId") or "").strip()
            and str(hit.get("specNo") or "").strip() not in excluded_specs
            and (
                str(hit.get("specNo") or "").strip(),
                str(hit.get("clauseId") or "").strip(),
            )
            not in excluded_clause_pairs
        ]
