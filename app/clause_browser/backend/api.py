from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import asyncio
from urllib.parse import quote, urlsplit, urlunsplit

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.clause_browser.backend.repository import ClauseRepository
from app.clause_browser.backend.services import (
    DocxExportService,
    LLMActionCancelledError,
    LLMActionQueueFullError,
    LLMActionService,
    SpecbotQueryService,
    sanitize_file_stem,
)


class ClauseTreePayload(BaseModel):
    key: str
    specNo: str
    specTitle: str | None = None
    clauseId: str
    clauseTitle: str
    text: str = ""
    parentClauseId: str | None = None
    clausePath: list[str] = Field(default_factory=list)
    sourceFile: str | None = None
    orderInSource: int | None = None
    blocks: list[dict[str, Any]] = Field(default_factory=list)
    children: list["ClauseTreePayload"] = Field(default_factory=list)


ClauseTreePayload.model_rebuild()


class ExportRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    roots: list[ClauseTreePayload] = Field(min_length=1)
    notes: list[dict[str, Any]] = Field(default_factory=list)
    highlights: list[dict[str, Any]] = Field(default_factory=list)


class LLMActionRequest(BaseModel):
    actionType: str = Field(min_length=1, max_length=50)
    text: str = Field(min_length=1, max_length=200000)
    sourceLanguage: str = Field(min_length=2, max_length=16)
    targetLanguage: str = Field(min_length=2, max_length=16)
    context: str | None = Field(default=None, max_length=2000)


@dataclass(frozen=True)
class ClauseBrowserConfig:
    languages: list[dict[str, str]]
    actions: list[dict[str, str]]
    release_scopes: list[dict[str, str]]
    duplicate_policy: str = "focus-existing"
    specbot_defaults: dict[str, Any] | None = None
    query_api_url: str | None = None


class SpecbotSettingsPayload(BaseModel):
    baseUrl: str = Field(min_length=1, max_length=200)
    configBaseUrl: str = Field(default="", max_length=200)
    limit: int = Field(default=4, ge=1, le=20)
    iterations: int = Field(default=1, ge=0, le=10)
    nextIterationLimit: int = Field(default=2, ge=1, le=20)
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


def create_router(
    *,
    repository: ClauseRepository,
    export_service: DocxExportService,
    llm_service,
    config: ClauseBrowserConfig,
    rich_document_service=None,
    specbot_service: SpecbotQueryService | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/clause-browser", tags=["clause-browser"])

    @router.get("/config")
    def get_config(request: Request) -> dict[str, Any]:
        return success(
            {
                "languages": config.languages,
                "actions": config.actions,
                "releaseScopes": config.release_scopes,
                "duplicatePolicy": config.duplicate_policy,
                "corpusPath": str(repository.corpus_path),
                "specbotDefaults": config.specbot_defaults or {},
                "queryApiUrl": _resolve_public_query_api_url(request, config.query_api_url),
            }
        )

    @router.get("/documents")
    def list_documents(
        query: str = "",
        clauseQuery: str = "",
        limit: int = 50,
        releaseData: str = "",
        release: str = "",
    ) -> dict[str, Any]:
        return success(
            {
                "items": [
                    item.to_dict()
                    for item in repository.list_documents(
                        query=query,
                        clause_query=clauseQuery,
                        limit=limit,
                        release_data=releaseData,
                        release=release,
                    )
                ]
            }
        )

    @router.get("/documents/{spec_no}/clauses")
    def list_clauses(
        spec_no: str,
        query: str = "",
        limit: int = 100,
        includeAll: bool = False,
        releaseData: str = "",
        release: str = "",
    ) -> dict[str, Any]:
        try:
            items = repository.list_clauses(
                spec_no=spec_no,
                query=query,
                limit=limit,
                include_all=includeAll,
                release_data=releaseData,
                release=release,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return success({"items": [item.to_dict() for item in items]})

    @router.get("/documents/{spec_no}/clauses/{clause_id:path}/subtree")
    def get_subtree(spec_no: str, clause_id: str, releaseData: str = "", release: str = "") -> dict[str, Any]:
        try:
            if rich_document_service is not None:
                try:
                    return success(
                        rich_document_service.get_subtree(spec_no=spec_no, clause_id=clause_id).to_dict()
                    )
                except Exception:
                    return success(
                        repository.get_subtree(
                            spec_no=spec_no,
                            clause_id=clause_id,
                            release_data=releaseData,
                            release=release,
                        ).to_dict()
                    )
            return success(
                repository.get_subtree(
                    spec_no=spec_no,
                    clause_id=clause_id,
                    release_data=releaseData,
                    release=release,
                ).to_dict()
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/exports/docx")
    def export_docx(request: ExportRequest) -> dict[str, Any]:
        try:
            result = export_service.export(
                title=request.title,
                roots=[root.model_dump(mode="json") for root in request.roots],
                notes=request.notes,
                highlights=request.highlights,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(status_code=500, detail=f"DOCX export failed: {exc}") from exc
        return success(result.to_dict())

    @router.post("/exports/docx/download")
    def export_docx_download(request: ExportRequest) -> Response:
        try:
            file_name, payload = export_service.export_bytes(
                title=request.title,
                roots=[root.model_dump(mode="json") for root in request.roots],
                notes=request.notes,
                highlights=request.highlights,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(status_code=500, detail=f"DOCX export failed: {exc}") from exc
        stem = file_name[:-5] if file_name.lower().endswith(".docx") else file_name
        ascii_stem = sanitize_file_stem(stem.encode("ascii", "ignore").decode("ascii"))
        if not any(char.isalnum() for char in ascii_stem):
            ascii_stem = "clause-export"
        ascii_name = f"{ascii_stem}.docx"
        headers = {
            "Content-Disposition": (
                f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{quote(file_name)}'
            )
        }
        return Response(
            content=payload,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers=headers,
        )

    @router.post("/llm-actions")
    async def run_llm_action(request: Request, payload: LLMActionRequest) -> dict[str, Any]:
        disconnect_event = asyncio.Event()

        async def watch_disconnect() -> None:
            if request is None:
                return
            while not disconnect_event.is_set():
                if await request.is_disconnected():
                    disconnect_event.set()
                    return
                await asyncio.sleep(0.2)

        watcher = asyncio.create_task(watch_disconnect())
        try:
            if hasattr(llm_service, "run_async"):
                result = await llm_service.run_async(
                    action_type=payload.actionType,
                    text=payload.text,
                    source_language=payload.sourceLanguage,
                    target_language=payload.targetLanguage,
                    context=payload.context,
                    should_cancel=disconnect_event.is_set,
                )
            else:
                result = llm_service.run_limited(
                    action_type=payload.actionType,
                    text=payload.text,
                    source_language=payload.sourceLanguage,
                    target_language=payload.targetLanguage,
                    context=payload.context,
                    should_cancel=disconnect_event.is_set,
                )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except LLMActionQueueFullError as exc:
            raise HTTPException(status_code=429, detail=str(exc)) from exc
        except LLMActionCancelledError as exc:
            raise HTTPException(status_code=499, detail=str(exc)) from exc
        except Exception as exc:  # pragma: no cover
            raise HTTPException(status_code=502, detail=f"LLM action failed: {exc}") from exc
        finally:
            disconnect_event.set()
            watcher.cancel()
        return success(result)

    @router.post("/specbot/query")
    async def run_specbot_query(request: Request, payload: SpecbotQueryRequest) -> dict[str, Any]:
        if specbot_service is None:
            raise HTTPException(status_code=503, detail="SpecBot query service is unavailable.")
        disconnect_event = asyncio.Event()

        async def watch_disconnect() -> None:
            if request is None:
                return
            while not disconnect_event.is_set():
                if await request.is_disconnected():
                    disconnect_event.set()
                    return
                await asyncio.sleep(0.2)

        watcher = asyncio.create_task(watch_disconnect())
        try:
            if hasattr(specbot_service, "run_async"):
                result = await specbot_service.run_async(
                    query=payload.query,
                    release_data=payload.releaseData,
                    release=payload.release,
                    settings=payload.settings.model_dump(mode="json") if payload.settings else None,
                    exclude_specs=payload.excludeSpecs,
                    exclude_clauses=[item.model_dump(mode="json") for item in payload.excludeClauses],
                    should_cancel=disconnect_event.is_set,
                )
            else:
                result = specbot_service.run(
                    query=payload.query,
                    release_data=payload.releaseData,
                    release=payload.release,
                    settings=payload.settings.model_dump(mode="json") if payload.settings else None,
                    exclude_specs=payload.excludeSpecs,
                    exclude_clauses=[item.model_dump(mode="json") for item in payload.excludeClauses],
                )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except LLMActionQueueFullError as exc:
            raise HTTPException(status_code=429, detail=str(exc)) from exc
        except LLMActionCancelledError as exc:
            raise HTTPException(status_code=499, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=f"SpecBot query failed: {exc}") from exc
        finally:
            disconnect_event.set()
            watcher.cancel()
        hits = result.get("hits") or []
        valid_hits = [
            hit
            for hit in hits
            if repository.has_clause(
                str(hit.get("specNo") or "").strip(),
                str(hit.get("clauseId") or "").strip(),
                release_data=payload.releaseData or "",
                release=payload.release or "",
            )
        ]
        filtered_count = len(hits) - len(valid_hits)
        return success({**result, "hits": valid_hits, "filteredInvalidHits": filtered_count})

    return router


def success(data: Any) -> dict[str, Any]:
    return {"success": True, "data": data}


def _resolve_public_query_api_url(request: Request, configured_url: str | None) -> str | None:
    if not configured_url:
        return None
    parts = urlsplit(configured_url)
    if not parts.scheme or not parts.netloc:
        return configured_url
    hostname = parts.hostname or ""
    if hostname not in {"127.0.0.1", "localhost", "::1"}:
        return configured_url
    public_host = request.url.hostname or hostname
    netloc = public_host
    if parts.port:
        netloc = f"{public_host}:{parts.port}"
    return urlunsplit((parts.scheme or request.url.scheme, netloc, parts.path, parts.query, parts.fragment))
