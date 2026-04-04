from __future__ import annotations

import asyncio
import logging
import os
import threading
import json
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
from app.shared_task_limiter import SharedTaskLimiter
from app.specbot_query_engine import PersistentSpecbotQueryEngine, SpecbotQueryServerSettings
from embedding.config import DEFAULT_EMBEDDING_DEVICE, DEFAULT_EMBEDDING_MODEL
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
    actionScope: str | None = Field(default=None, min_length=1, max_length=50)
    text: str = Field(min_length=1, max_length=200000)
    sourceLanguage: str = Field(min_length=2, max_length=16)
    targetLanguage: str = Field(min_length=2, max_length=16)
    context: str | None = Field(default=None, max_length=2000)



def create_app(settings: SpecbotQueryServerSettings | None = None) -> FastAPI:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    active_settings = settings or load_settings()
    engine = PersistentSpecbotQueryEngine(active_settings)
    llm_service = LLMActionService(
        provider=active_settings.llm_action_provider,
        model=active_settings.llm_action_model,
        system_prompt_path=active_settings.project_root / "system_prompt_clause_summary.txt",
        user_prompt_path=active_settings.project_root / "user_prompt_clause_summary.txt",
        selection_system_prompt_path=active_settings.project_root / "system_prompt_translate.txt",
        selection_user_prompt_path=active_settings.project_root / "user_prompt_translate.txt",
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
                action_scope=payload.actionScope,
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
                    action_scope=payload.actionScope,
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
