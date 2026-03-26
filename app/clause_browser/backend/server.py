from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.clause_browser.backend.api import ClauseBrowserConfig, create_router
from app.clause_browser.backend.render_parser import RichClauseDocumentService
from app.clause_browser.backend.repository import ClauseRepository
from app.clause_browser.backend.services import DocxExportService, LLMActionService, SpecbotQueryHttpService


DEFAULT_CORPUS_PATH = Path("artifacts/clause_browser_corpus.jsonl")
DEFAULT_EXPORT_DIR = Path("artifacts/clause_exports")
DEFAULT_MEDIA_DIR = Path("artifacts/clause_browser_media")
STATIC_DIR = Path(__file__).resolve().parents[1] / "frontend" / "static"


@dataclass(frozen=True)
class ClauseBrowserSettings:
    project_root: Path
    corpus_path: Path
    export_dir: Path
    media_dir: Path
    cors_origins: tuple[str, ...]
    llm_provider: str
    llm_model: str
    languages: tuple[tuple[str, str], ...]
    specbot_query_api_url: str


def create_app(settings: ClauseBrowserSettings | None = None, specbot_service=None) -> FastAPI:
    active_settings = settings or load_settings()
    repository = ClauseRepository(active_settings.corpus_path)
    export_service = DocxExportService(
        export_dir=active_settings.export_dir,
        project_root=active_settings.project_root,
    )
    rich_document_service = None
    if active_settings.corpus_path.name != "clause_browser_corpus.jsonl":
        rich_document_service = RichClauseDocumentService(
            base_repository=repository,
            media_root=active_settings.media_dir,
        )
    llm_service = LLMActionService(
        provider=active_settings.llm_provider,
        model=active_settings.llm_model,
        system_prompt_path=active_settings.project_root / "system_prompt_translate.txt",
        user_prompt_path=active_settings.project_root / "user_prompt_translate.txt",
    )
    active_specbot_service = specbot_service or SpecbotQueryHttpService(base_url=active_settings.specbot_query_api_url)

    app = FastAPI(title="Specbot Clause Browser", version="0.1.0")
    if active_settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(active_settings.cors_origins),
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    app.include_router(
        create_router(
            repository=repository,
            export_service=export_service,
            llm_service=llm_service,
            config=ClauseBrowserConfig(
                languages=[{"code": code, "label": label} for code, label in active_settings.languages],
                actions=llm_service.available_actions(),
                specbot_defaults=active_specbot_service.defaults.to_dict(),
            ),
            rich_document_service=rich_document_service,
            specbot_service=active_specbot_service,
        )
    )

    app.mount("/clause-browser", StaticFiles(directory=str(STATIC_DIR), html=True), name="clause-browser")
    app.mount("/clause-browser-media", StaticFiles(directory=str(active_settings.media_dir)), name="clause-browser-media")

    @app.get("/", include_in_schema=False)
    def root_redirect() -> RedirectResponse:
        return RedirectResponse(url="/clause-browser/")

    @app.get("/health", include_in_schema=False)
    def health() -> dict[str, object]:
        return {"ok": True, "corpusPath": str(active_settings.corpus_path)}

    return app


def load_settings() -> ClauseBrowserSettings:
    project_root = Path(__file__).resolve().parents[3]
    corpus_path = Path(os.environ.get("SPECBOT_CLAUSE_BROWSER_CORPUS", DEFAULT_CORPUS_PATH))
    if not corpus_path.is_absolute():
        corpus_path = project_root / corpus_path

    export_dir = Path(os.environ.get("SPECBOT_CLAUSE_BROWSER_EXPORT_DIR", DEFAULT_EXPORT_DIR))
    if not export_dir.is_absolute():
        export_dir = project_root / export_dir
    media_dir = Path(os.environ.get("SPECBOT_CLAUSE_BROWSER_MEDIA_DIR", DEFAULT_MEDIA_DIR))
    if not media_dir.is_absolute():
        media_dir = project_root / media_dir

    cors_env = os.environ.get("SPECBOT_CLAUSE_BROWSER_CORS_ORIGINS", "").strip()
    cors_origins = tuple(part.strip() for part in cors_env.split(",") if part.strip())
    llm_provider = os.environ.get("SPECBOT_LLM_ACTION_PROVIDER", "openai").strip() or "openai"
    llm_model = os.environ.get("SPECBOT_LLM_ACTION_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
    specbot_query_api_url = os.environ.get("SPECBOT_QUERY_API_URL", "http://127.0.0.1:8010").strip() or "http://127.0.0.1:8010"

    languages_env = os.environ.get("SPECBOT_CLAUSE_BROWSER_LANGUAGES", "ko:Korean,en:English")
    languages: list[tuple[str, str]] = []
    for raw_item in languages_env.split(","):
        raw_item = raw_item.strip()
        if not raw_item:
            continue
        if ":" in raw_item:
            code, label = raw_item.split(":", maxsplit=1)
            languages.append((code.strip(), label.strip() or code.strip()))
        else:
            languages.append((raw_item, raw_item))
    if not languages:
        languages = [("ko", "Korean"), ("en", "English")]

    return ClauseBrowserSettings(
        project_root=project_root,
        corpus_path=corpus_path,
        export_dir=export_dir,
        media_dir=media_dir,
        cors_origins=cors_origins,
        llm_provider=llm_provider,
        llm_model=llm_model,
        languages=tuple(languages),
        specbot_query_api_url=specbot_query_api_url,
    )
