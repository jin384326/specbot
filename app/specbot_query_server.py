from __future__ import annotations

import asyncio
import logging
import os
import threading
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.clause_browser.services import (
    LLMActionCancelledError,
    LLMActionQueueFullError,
    LLMActionService,
    SpecbotQueryDefaults,
)
from embedding.config import DEFAULT_EMBEDDING_DEVICE, DEFAULT_EMBEDDING_MODEL
from embedding.registry import create_embedding_provider
from retrieval.iterative_llm_retriever import ChatOpenAIRelevanceJudge, IterativeLLMRetriever, RetrievalCancelledError
from retrieval.query_normalizer import QueryFeatureRegistry
from retrieval.vespa_multi_hop_backend import VespaMultiHopBackend
from vespa.http_adapter import VespaEndpoint


logger = logging.getLogger(__name__)


class SpecbotSettingsPayload(BaseModel):
    baseUrl: str = Field(min_length=1, max_length=200)
    configBaseUrl: str = Field(default="", max_length=200)
    limit: int = Field(default=4, ge=1, le=20)
    iterations: int = Field(default=1, ge=0, le=10)
    nextIterationLimit: int = Field(default=2, ge=1, le=20)
    followupMode: str = Field(default="sentence-summary", pattern="^(keyword|sentence-summary)$")
    summary: str = Field(default="short", min_length=1, max_length=50)
    registry: str = Field(min_length=1, max_length=500)
    localModelDir: str = Field(min_length=1, max_length=500)
    device: str = Field(default="cuda", min_length=1, max_length=50)
    sparseBoost: float = Field(default=0.0, ge=0.0, le=10.0)
    vectorBoost: float = Field(default=1.0, ge=0.0, le=10.0)


class ClauseExclusionPayload(BaseModel):
    specNo: str = Field(min_length=1, max_length=32)
    clauseId: str = Field(min_length=1, max_length=128)


class SpecbotQueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    releaseData: str | None = Field(default=None, max_length=32)
    release: str | None = Field(default=None, max_length=32)
    settings: SpecbotSettingsPayload | None = None
    excludeSpecs: list[str] = Field(default_factory=list)
    excludeClauses: list[ClauseExclusionPayload] = Field(default_factory=list)


class LLMActionRequest(BaseModel):
    actionType: str = Field(min_length=1, max_length=50)
    text: str = Field(min_length=1, max_length=200000)
    sourceLanguage: str = Field(min_length=2, max_length=16)
    targetLanguage: str = Field(min_length=2, max_length=16)
    context: str | None = Field(default=None, max_length=2000)


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


class SharedTaskLimiter:
    def __init__(self, max_concurrent_tasks: int, max_queued_tasks: int) -> None:
        self._max_concurrent_tasks = max(1, int(max_concurrent_tasks))
        self._max_queued_tasks = max(0, int(max_queued_tasks))
        self._lock = asyncio.Lock()
        self._active_tasks = 0
        self._accepted_tasks = 0
        self._queue: asyncio.Queue[_QueuedTask] = asyncio.Queue()
        self._workers: list[asyncio.Task] = []
        self._started = False

    async def start(self) -> None:
        if self._started:
            return
        self._started = True
        self._workers = [asyncio.create_task(self._worker_loop()) for _ in range(self._max_concurrent_tasks)]

    async def shutdown(self) -> None:
        for worker in self._workers:
            worker.cancel()
        for worker in self._workers:
            try:
                await worker
            except asyncio.CancelledError:
                pass
        self._workers.clear()
        self._started = False

    async def run_async(self, fn, *args, should_cancel=None, on_status_change=None, **kwargs):
        await self.start()
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        queued_position = 0
        job = _QueuedTask(
            fn=fn,
            args=args,
            kwargs=kwargs,
            future=future,
            should_cancel=should_cancel,
            on_status_change=on_status_change,
        )
        async with self._lock:
            if self._accepted_tasks >= self._max_concurrent_tasks + self._max_queued_tasks:
                raise LLMActionQueueFullError(
                    "The shared query/translation queue is full. Wait for current tasks to finish and try again."
                )
            queued_position = max(0, self._accepted_tasks - self._active_tasks)
            self._accepted_tasks += 1
            self._queue.put_nowait(job)
        if on_status_change is not None:
            on_status_change(
                {
                    "state": "queued",
                    "queued_position": queued_position + 1,
                    "active_tasks": self._active_tasks,
                    "accepted_tasks": self._accepted_tasks,
                }
            )

        while True:
            if should_cancel and should_cancel():
                job.cancelled = True
                if not future.done():
                    future.set_exception(LLMActionCancelledError("Task cancelled by client."))
                raise LLMActionCancelledError("Task cancelled by client.")
            try:
                return await asyncio.wait_for(asyncio.shield(future), timeout=0.2)
            except asyncio.TimeoutError:
                continue

    async def _worker_loop(self) -> None:
        while True:
            job = await self._queue.get()
            async with self._lock:
                self._active_tasks += 1
                active_tasks = self._active_tasks
                accepted_tasks = self._accepted_tasks
            try:
                if job.on_status_change is not None:
                    job.on_status_change(
                        {
                            "state": "started",
                            "active_tasks": active_tasks,
                            "accepted_tasks": accepted_tasks,
                        }
                    )
                if job.cancelled or job.future.done() or (job.should_cancel and job.should_cancel()):
                    if not job.future.done():
                        job.future.set_exception(LLMActionCancelledError("Task cancelled by client."))
                    continue
                result = await asyncio.to_thread(job.fn, *job.args, **job.kwargs)
                if not job.future.done():
                    job.future.set_result(result)
            except Exception as exc:
                if not job.future.done():
                    job.future.set_exception(exc)
            finally:
                async with self._lock:
                    self._active_tasks = max(0, self._active_tasks - 1)
                    self._accepted_tasks = max(0, self._accepted_tasks - 1)
                self._queue.task_done()


@dataclass
class _QueuedTask:
    fn: Any
    args: tuple[Any, ...]
    kwargs: dict[str, Any]
    future: asyncio.Future
    should_cancel: Any = None
    on_status_change: Any = None
    cancelled: bool = field(default=False)


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


def create_app(settings: SpecbotQueryServerSettings | None = None) -> FastAPI:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    active_settings = settings or load_settings()
    engine = PersistentSpecbotQueryEngine(active_settings)
    llm_service = LLMActionService(
        provider=active_settings.llm_action_provider,
        model=active_settings.llm_action_model,
        system_prompt_path=active_settings.project_root / "system_prompt_translate.txt",
        user_prompt_path=active_settings.project_root / "user_prompt_translate.txt",
    )
    task_limiter = SharedTaskLimiter(
        max_concurrent_tasks=active_settings.task_max_concurrency,
        max_queued_tasks=active_settings.task_max_queue_size,
    )
    app = FastAPI(title="SpecBot Query API", version="0.1.0")
    if active_settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(active_settings.cors_origins),
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.on_event("startup")
    async def startup_event() -> None:
        await task_limiter.start()

    @app.on_event("shutdown")
    async def shutdown_event() -> None:
        await task_limiter.shutdown()

    @app.get("/health", include_in_schema=False)
    def health() -> dict[str, object]:
        return {"ok": True, "baseUrl": active_settings.defaults.base_url}

    @app.get("/config")
    def config() -> dict[str, object]:
        return {"defaults": engine.defaults.to_dict()}

    async def watch_disconnect(request: Request, cancel_event: threading.Event) -> None:
        while not cancel_event.is_set():
            if await request.is_disconnected():
                cancel_event.set()
                return
            await asyncio.sleep(0.2)

    @app.post("/llm-actions")
    async def llm_actions(request: Request, payload: LLMActionRequest) -> dict[str, object]:
        cancel_event = threading.Event()
        watcher = asyncio.create_task(watch_disconnect(request, cancel_event))
        try:
            return await task_limiter.run_async(
                llm_service.run,
                action_type=payload.actionType,
                text=payload.text,
                source_language=payload.sourceLanguage,
                target_language=payload.targetLanguage,
                context=payload.context,
                should_cancel=cancel_event.is_set,
            )
        except LLMActionQueueFullError as exc:
            raise HTTPException(status_code=429, detail=str(exc)) from exc
        except LLMActionCancelledError as exc:
            raise HTTPException(status_code=499, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        finally:
            cancel_event.set()
            watcher.cancel()

    @app.post("/llm-actions-stream")
    async def llm_actions_stream(request: Request, payload: LLMActionRequest) -> StreamingResponse:
        cancel_event = threading.Event()
        event_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def on_task_status_change(status_payload: dict[str, Any]) -> None:
            loop.call_soon_threadsafe(
                event_queue.put_nowait,
                {
                    "type": "status",
                    "status": str(status_payload.get("state") or ""),
                    "queuedPosition": int(status_payload.get("queued_position") or 0),
                    "activeTasks": int(status_payload.get("active_tasks") or 0),
                    "acceptedTasks": int(status_payload.get("accepted_tasks") or 0),
                },
            )

        watcher = asyncio.create_task(watch_disconnect(request, cancel_event))

        async def produce() -> None:
            try:
                result = await task_limiter.run_async(
                    llm_service.run,
                    action_type=payload.actionType,
                    text=payload.text,
                    source_language=payload.sourceLanguage,
                    target_language=payload.targetLanguage,
                    context=payload.context,
                    on_status_change=on_task_status_change,
                    should_cancel=cancel_event.is_set,
                )
                await event_queue.put({"type": "done", "result": result})
            except LLMActionQueueFullError as exc:
                await event_queue.put({"type": "error", "status": 429, "detail": str(exc)})
            except LLMActionCancelledError as exc:
                await event_queue.put({"type": "error", "status": 499, "detail": str(exc)})
            except ValueError as exc:
                await event_queue.put({"type": "error", "status": 400, "detail": str(exc)})
            except Exception as exc:
                await event_queue.put({"type": "error", "status": 502, "detail": str(exc)})
            finally:
                cancel_event.set()
                await event_queue.put({"type": "close"})

        producer = asyncio.create_task(produce())

        async def stream():
            try:
                while True:
                    event = await event_queue.get()
                    if event.get("type") == "close":
                        break
                    yield json.dumps(event, ensure_ascii=False) + "\n"
            finally:
                cancel_event.set()
                watcher.cancel()
                producer.cancel()

        return StreamingResponse(stream(), media_type="application/x-ndjson")

    @app.post("/query")
    async def query(request: Request, payload: SpecbotQueryRequest) -> dict[str, object]:
        cancel_event = threading.Event()
        watcher = asyncio.create_task(watch_disconnect(request, cancel_event))
        try:
            return await task_limiter.run_async(
                engine.run,
                payload.query.strip(),
                payload.settings.model_dump(mode="json") if payload.settings else None,
                payload.excludeSpecs,
                [item.model_dump(mode="json") for item in payload.excludeClauses],
                payload.releaseData,
                payload.release,
                cancel_event.is_set,
                should_cancel=cancel_event.is_set,
            )
        except RetrievalCancelledError as exc:
            raise HTTPException(status_code=499, detail=str(exc)) from exc
        except LLMActionQueueFullError as exc:
            raise HTTPException(status_code=429, detail=str(exc)) from exc
        except LLMActionCancelledError as exc:
            raise HTTPException(status_code=499, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        finally:
            cancel_event.set()
            watcher.cancel()

    @app.post("/query-stream")
    async def query_stream(request: Request, payload: SpecbotQueryRequest) -> StreamingResponse:
        cancel_event = threading.Event()
        event_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        loop = asyncio.get_running_loop()
        streamed_pairs: set[tuple[str, str]] = set()

        def on_iteration_complete(iteration_payload: dict[str, Any]) -> None:
            hits = engine.iteration_hits(
                iteration_payload,
                exclude_specs=payload.excludeSpecs,
                exclude_clauses=[item.model_dump(mode="json") for item in payload.excludeClauses],
            )
            if not hits:
                return
            loop.call_soon_threadsafe(
                event_queue.put_nowait,
                {
                    "type": "hits",
                    "iteration": int(iteration_payload.get("iteration") or 0),
                    "hits": hits,
                },
            )

        def on_relevant_result(result_payload: dict[str, Any]) -> None:
            hit = PersistentSpecbotQueryEngine.iteration_hits(
                {"results": [result_payload]},
                exclude_specs=payload.excludeSpecs,
                exclude_clauses=[item.model_dump(mode="json") for item in payload.excludeClauses],
            )
            if not hit:
                return
            item = hit[0]
            pair = (str(item.get("specNo") or "").strip(), str(item.get("clauseId") or "").strip())
            if not pair[0] or not pair[1] or pair in streamed_pairs:
                return
            streamed_pairs.add(pair)
            loop.call_soon_threadsafe(event_queue.put_nowait, {"type": "hit", "hit": item})

        def on_task_status_change(status_payload: dict[str, Any]) -> None:
            loop.call_soon_threadsafe(
                event_queue.put_nowait,
                {
                    "type": "status",
                    "status": str(status_payload.get("state") or ""),
                    "queuedPosition": int(status_payload.get("queued_position") or 0),
                    "activeTasks": int(status_payload.get("active_tasks") or 0),
                    "acceptedTasks": int(status_payload.get("accepted_tasks") or 0),
                },
            )

        watcher = asyncio.create_task(watch_disconnect(request, cancel_event))

        async def produce() -> None:
            try:
                result = await task_limiter.run_async(
                    engine.run,
                    payload.query.strip(),
                    payload.settings.model_dump(mode="json") if payload.settings else None,
                    payload.excludeSpecs,
                    [item.model_dump(mode="json") for item in payload.excludeClauses],
                    payload.releaseData,
                    payload.release,
                    cancel_event.is_set,
                    on_status_change=on_task_status_change,
                    on_iteration_complete=on_iteration_complete,
                    on_relevant_result=on_relevant_result,
                    should_cancel=cancel_event.is_set,
                )
                await event_queue.put(
                    {
                        "type": "done",
                        "query": result.get("query", payload.query.strip()),
                        "hits": result.get("hits", []),
                    }
                )
            except LLMActionQueueFullError as exc:
                await event_queue.put({"type": "error", "status": 429, "detail": str(exc)})
            except (LLMActionCancelledError, RetrievalCancelledError) as exc:
                await event_queue.put({"type": "error", "status": 499, "detail": str(exc)})
            except ValueError as exc:
                await event_queue.put({"type": "error", "status": 400, "detail": str(exc)})
            except Exception as exc:
                await event_queue.put({"type": "error", "status": 502, "detail": str(exc)})
            finally:
                cancel_event.set()
                await event_queue.put({"type": "close"})

        producer = asyncio.create_task(produce())

        async def stream():
            try:
                while True:
                    event = await event_queue.get()
                    if event.get("type") == "close":
                        break
                    yield json.dumps(event, ensure_ascii=False) + "\n"
            finally:
                cancel_event.set()
                watcher.cancel()
                producer.cancel()

        return StreamingResponse(stream(), media_type="application/x-ndjson")

    return app


def load_settings() -> SpecbotQueryServerSettings:
    project_root = Path(__file__).resolve().parents[1]
    cors_env = os.environ.get("SPECBOT_QUERY_API_CORS_ORIGINS", "*").strip()
    cors_origins = tuple(part.strip() for part in cors_env.split(",") if part.strip())
    defaults = SpecbotQueryDefaults(
        base_url=os.environ.get("SPECBOT_QUERY_BASE_URL", "http://localhost:8080").strip() or "http://localhost:8080",
        config_base_url=os.environ.get("SPECBOT_QUERY_CONFIG_BASE_URL", "http://localhost:19071").strip() or "http://localhost:19071",
        limit=int(os.environ.get("SPECBOT_QUERY_LIMIT", "4")),
        iterations=int(os.environ.get("SPECBOT_QUERY_ITERATIONS", "1")),
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
        llm_action_provider=os.environ.get("SPECBOT_LLM_ACTION_PROVIDER", "openai").strip() or "openai",
        llm_action_model=os.environ.get("SPECBOT_LLM_ACTION_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini",
        timeout_seconds=float(os.environ.get("SPECBOT_QUERY_TIMEOUT", "30")),
        ranking=os.environ.get("SPECBOT_QUERY_RANKING", "hybrid").strip() or "hybrid",
        schema=os.environ.get("SPECBOT_QUERY_SCHEMA", "spec_finder").strip() or "spec_finder",
        namespace=os.environ.get("SPECBOT_QUERY_NAMESPACE", "spec_finder").strip() or "spec_finder",
        anchor_boost=float(os.environ.get("SPECBOT_QUERY_ANCHOR_BOOST", "1.15")),
        title_boost=float(os.environ.get("SPECBOT_QUERY_TITLE_BOOST", "1.2")),
        stage_boost=float(os.environ.get("SPECBOT_QUERY_STAGE_BOOST", "1.1")),
        task_max_concurrency=max(1, int(os.environ.get("SPECBOT_TASK_MAX_CONCURRENCY", "2"))),
        task_max_queue_size=max(0, int(os.environ.get("SPECBOT_TASK_MAX_QUEUE_SIZE", "5"))),
        cors_origins=cors_origins,
    )
