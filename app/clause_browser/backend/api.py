from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.clause_browser.backend.repository import ClauseRepository
from app.clause_browser.backend.services import DocxExportService, LLMActionService, SpecbotQueryService


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
    children: list["ClauseTreePayload"] = Field(default_factory=list)


ClauseTreePayload.model_rebuild()


class ExportRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    roots: list[ClauseTreePayload] = Field(min_length=1)


class LLMActionRequest(BaseModel):
    actionType: str = Field(min_length=1, max_length=50)
    text: str = Field(min_length=1, max_length=20000)
    sourceLanguage: str = Field(min_length=2, max_length=16)
    targetLanguage: str = Field(min_length=2, max_length=16)
    context: str | None = Field(default=None, max_length=500)


@dataclass(frozen=True)
class ClauseBrowserConfig:
    languages: list[dict[str, str]]
    actions: list[dict[str, str]]
    duplicate_policy: str = "focus-existing"
    specbot_defaults: dict[str, Any] | None = None


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


class ClauseExclusionPayload(BaseModel):
    specNo: str = Field(min_length=1, max_length=32)
    clauseId: str = Field(min_length=1, max_length=128)


class SpecbotQueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    settings: SpecbotSettingsPayload | None = None
    excludeSpecs: list[str] = Field(default_factory=list)
    excludeClauses: list[ClauseExclusionPayload] = Field(default_factory=list)


def create_router(
    *,
    repository: ClauseRepository,
    export_service: DocxExportService,
    llm_service: LLMActionService,
    config: ClauseBrowserConfig,
    rich_document_service=None,
    specbot_service: SpecbotQueryService | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/clause-browser", tags=["clause-browser"])

    @router.get("/config")
    def get_config() -> dict[str, Any]:
        return success(
            {
                "languages": config.languages,
                "actions": config.actions,
                "duplicatePolicy": config.duplicate_policy,
                "corpusPath": str(repository.corpus_path),
                "specbotDefaults": config.specbot_defaults or {},
            }
        )

    @router.get("/documents")
    def list_documents(query: str = "", limit: int = 50) -> dict[str, Any]:
        return success({"items": [item.to_dict() for item in repository.list_documents(query=query, limit=limit)]})

    @router.get("/documents/{spec_no}/clauses")
    def list_clauses(spec_no: str, query: str = "", limit: int = 100, includeAll: bool = False) -> dict[str, Any]:
        try:
            items = repository.list_clauses(spec_no=spec_no, query=query, limit=limit, include_all=includeAll)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return success({"items": [item.to_dict() for item in items]})

    @router.get("/documents/{spec_no}/clauses/{clause_id:path}/subtree")
    def get_subtree(spec_no: str, clause_id: str) -> dict[str, Any]:
        try:
            if rich_document_service is not None:
                try:
                    return success(rich_document_service.get_subtree(spec_no=spec_no, clause_id=clause_id).to_dict())
                except Exception:
                    return success(repository.get_subtree(spec_no=spec_no, clause_id=clause_id).to_dict())
            return success(repository.get_subtree(spec_no=spec_no, clause_id=clause_id).to_dict())
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/exports/docx")
    def export_docx(request: ExportRequest) -> dict[str, Any]:
        try:
            result = export_service.export(
                title=request.title,
                roots=[root.model_dump(mode="json") for root in request.roots],
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(status_code=500, detail=f"DOCX export failed: {exc}") from exc
        return success(result.to_dict())

    @router.post("/llm-actions")
    def run_llm_action(request: LLMActionRequest) -> dict[str, Any]:
        try:
            result = llm_service.run(
                action_type=request.actionType,
                text=request.text,
                source_language=request.sourceLanguage,
                target_language=request.targetLanguage,
                context=request.context,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:  # pragma: no cover
            raise HTTPException(status_code=502, detail=f"LLM action failed: {exc}") from exc
        return success(result)

    @router.post("/specbot/query")
    def run_specbot_query(request: SpecbotQueryRequest) -> dict[str, Any]:
        if specbot_service is None:
            raise HTTPException(status_code=503, detail="SpecBot query service is unavailable.")
        try:
            result = specbot_service.run(
                query=request.query,
                settings=request.settings.model_dump(mode="json") if request.settings else None,
                exclude_specs=request.excludeSpecs,
                exclude_clauses=[item.model_dump(mode="json") for item in request.excludeClauses],
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=f"SpecBot query failed: {exc}") from exc
        hits = result.get("hits") or []
        valid_hits = [
            hit
            for hit in hits
            if repository.has_clause(str(hit.get("specNo") or "").strip(), str(hit.get("clauseId") or "").strip())
        ]
        filtered_count = len(hits) - len(valid_hits)
        return success({**result, "hits": valid_hits, "filteredInvalidHits": filtered_count})

    return router


def success(data: Any) -> dict[str, Any]:
    return {"success": True, "data": data}
