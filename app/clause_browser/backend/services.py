from __future__ import annotations

import os
import re
import subprocess
import sys
import json
import asyncio
from urllib import error as urllib_error
from urllib import request as urllib_request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from docx import Document


INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
WHITESPACE_RUN = re.compile(r"\s+")
TRANSLATION_CHUNK_LIMIT = 12000


@dataclass(frozen=True)
class ExportResult:
    title: str
    file_name: str
    absolute_path: str
    relative_path: str
    clause_count: int

    def to_dict(self) -> dict[str, object]:
        return {
            "title": self.title,
            "fileName": self.file_name,
            "absolutePath": self.absolute_path,
            "relativePath": self.relative_path,
            "clauseCount": self.clause_count,
        }


class DocxExportService:
    def __init__(self, export_dir: str | Path, project_root: str | Path) -> None:
        self._export_dir = Path(export_dir)
        self._project_root = Path(project_root)
        self._export_dir.mkdir(parents=True, exist_ok=True)

    def export(self, title: str, roots: list[dict[str, Any]]) -> ExportResult:
        cleaned_title = title.strip()
        if not cleaned_title:
            raise ValueError("Document title is required.")
        if not roots:
            raise ValueError("At least one loaded clause is required to export a DOCX.")

        document = Document()
        document.add_heading(cleaned_title, level=0)
        clause_count = 0
        for root in roots:
            clause_count += self._write_clause(document, root, depth=0)

        file_name = self._allocate_file_name(cleaned_title)
        absolute_path = self._export_dir / file_name
        document.save(absolute_path)
        try:
            relative_path = absolute_path.relative_to(self._project_root)
        except ValueError:
            relative_path = absolute_path

        return ExportResult(
            title=cleaned_title,
            file_name=file_name,
            absolute_path=str(absolute_path),
            relative_path=str(relative_path),
            clause_count=clause_count,
        )

    def _allocate_file_name(self, title: str) -> str:
        base_name = sanitize_file_stem(title)
        candidate = f"{base_name}.docx"
        suffix = 2
        while (self._export_dir / candidate).exists():
            candidate = f"{base_name}-{suffix}.docx"
            suffix += 1
        return candidate

    def _write_clause(self, document: Document, clause: dict[str, Any], depth: int) -> int:
        clause_id = str(clause.get("clauseId") or "").strip()
        clause_title = str(clause.get("clauseTitle") or "").strip()
        heading_text = " ".join(part for part in [clause_id, clause_title] if part).strip() or clause_id or clause_title
        document.add_heading(heading_text, level=min(depth + 1, 9))

        body = str(clause.get("text") or "").strip()
        if body:
            for paragraph in body.splitlines():
                trimmed = paragraph.strip()
                if trimmed:
                    document.add_paragraph(trimmed)

        total = 1
        for child in clause.get("children") or []:
            total += self._write_clause(document, child, depth + 1)
        return total


class LLMActionService:
    def __init__(
        self,
        provider: str = "openai",
        model: str = "gpt-4o-mini",
        system_prompt_path: str | Path | None = None,
        user_prompt_path: str | Path | None = None,
    ) -> None:
        self._provider = provider
        self._model = model
        self._system_prompt = self._load_prompt(
            system_prompt_path,
            default=(
                "You are a professional 3GPP technical translator.\n"
                "Translate the provided context faithfully into Korean.\n"
                "Return only the translated text."
            ),
        )
        self._user_prompt_template = self._load_prompt(
            user_prompt_path,
            default="Translate the following 3GPP context into Korean.\n\n[CONTEXT]\n{context_text}",
        )

    def available_actions(self) -> list[dict[str, str]]:
        return [{"type": "translate", "label": "Translate"}]

    def run(
        self,
        *,
        action_type: str,
        text: str,
        source_language: str,
        target_language: str,
        context: str | None = None,
    ) -> dict[str, Any]:
        cleaned_text = text.strip()
        if not cleaned_text:
            raise ValueError("Select text before requesting an LLM action.")
        if action_type != "translate":
            raise ValueError(f"Unsupported action type: {action_type}")

        if self._provider == "openai":
            if not os.environ.get("OPENAI_API_KEY"):
                raise RuntimeError("OPENAI_API_KEY is not configured on the server.")
            return self._run_openai_translation(
                text=cleaned_text,
                source_language=source_language,
                target_language=target_language,
                context=context or "",
            )
        if self._provider == "mock":
            return self._run_mock_translation(
                text=cleaned_text,
                source_language=source_language,
                target_language=target_language,
            )
        raise RuntimeError(f"Unsupported LLM provider: {self._provider}")

    def _run_openai_translation(
        self,
        *,
        text: str,
        source_language: str,
        target_language: str,
        context: str,
    ) -> dict[str, Any]:
        try:
            from langchain_openai import ChatOpenAI
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(f"OpenAI provider is unavailable: {exc}") from exc

        client = ChatOpenAI(model=self._model, temperature=0)
        translated_parts: list[str] = []
        for chunk in self._split_translation_text(text):
            system_prompt = self._system_prompt
            context_text = chunk if not context else f"{context}\n\n{chunk}"
            human_prompt = self._user_prompt_template.replace("{context_text}", context_text)
            response = client.invoke([("system", system_prompt), ("human", human_prompt)])
            content = response.content if isinstance(response.content, str) else str(response.content)
            translated_parts.append(content.strip())
        return {
            "actionType": "translate",
            "provider": "openai",
            "model": self._model,
            "outputText": "\n\n".join(part for part in translated_parts if part),
            "sourceLanguage": source_language,
            "targetLanguage": target_language,
        }

    @staticmethod
    def _load_prompt(path: str | Path | None, *, default: str) -> str:
        if not path:
            return default
        prompt_path = Path(path)
        try:
            return prompt_path.read_text(encoding="utf-8").strip() or default
        except OSError:
            return default

    @staticmethod
    def _split_translation_text(text: str, limit: int = TRANSLATION_CHUNK_LIMIT) -> list[str]:
        cleaned = text.strip()
        if len(cleaned) <= limit:
            return [cleaned]

        paragraphs = [part.strip() for part in re.split(r"\n{2,}", cleaned) if part.strip()]
        if not paragraphs:
            paragraphs = [cleaned]

        chunks: list[str] = []
        current_parts: list[str] = []
        current_length = 0

        for paragraph in paragraphs:
            if len(paragraph) > limit:
                if current_parts:
                    chunks.append("\n\n".join(current_parts))
                    current_parts = []
                    current_length = 0
                start = 0
                while start < len(paragraph):
                    chunks.append(paragraph[start:start + limit].strip())
                    start += limit
                continue

            separator = 2 if current_parts else 0
            next_length = current_length + separator + len(paragraph)
            if current_parts and next_length > limit:
                chunks.append("\n\n".join(current_parts))
                current_parts = [paragraph]
                current_length = len(paragraph)
            else:
                current_parts.append(paragraph)
                current_length = next_length

        if current_parts:
            chunks.append("\n\n".join(current_parts))

        return [chunk for chunk in chunks if chunk]

    @staticmethod
    def _run_mock_translation(*, text: str, source_language: str, target_language: str) -> dict[str, Any]:
        return {
            "actionType": "translate",
            "provider": "mock",
            "model": "mock-translation",
            "outputText": f"[{source_language}->{target_language}] {text}",
            "sourceLanguage": source_language,
            "targetLanguage": target_language,
        }


def sanitize_file_stem(value: str) -> str:
    candidate = INVALID_FILENAME_CHARS.sub("", value.strip())
    candidate = WHITESPACE_RUN.sub("-", candidate)
    candidate = candidate.strip(".- ")
    return candidate or "clause-export"


@dataclass(frozen=True)
class SpecbotQueryDefaults:
    base_url: str = "http://localhost:8080"
    config_base_url: str = "http://localhost:19071"
    limit: int = 4
    iterations: int = 2
    next_iteration_limit: int = 2
    followup_mode: str = "sentence-summary"
    summary: str = "short"
    registry: str = "./artifacts/spec_query_registry.json"
    local_model_dir: str = "models/Qwen3-Embedding-0.6B"
    device: str = "cuda"
    sparse_boost: float = 0.0
    vector_boost: float = 1.0

    def to_dict(self) -> dict[str, object]:
        return {
            "baseUrl": self.base_url,
            "configBaseUrl": self.config_base_url,
            "limit": self.limit,
            "iterations": self.iterations,
            "nextIterationLimit": self.next_iteration_limit,
            "followupMode": self.followup_mode,
            "summary": self.summary,
            "registry": self.registry,
            "localModelDir": self.local_model_dir,
            "device": self.device,
            "sparseBoost": self.sparse_boost,
            "vectorBoost": self.vector_boost,
        }


class SpecbotQueryService:
    def __init__(self, project_root: str | Path, defaults: SpecbotQueryDefaults | None = None) -> None:
        self._project_root = Path(project_root)
        self._defaults = defaults or SpecbotQueryDefaults()

    @property
    def defaults(self) -> SpecbotQueryDefaults:
        return self._defaults

    def run(
        self,
        query: str,
        settings: dict[str, Any] | None = None,
        exclude_specs: list[str] | None = None,
        exclude_clauses: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        cleaned_query = query.strip()
        if not cleaned_query:
            raise ValueError("Query is required.")

        effective = self._merge_settings(settings or {})
        command = self._build_command(cleaned_query, effective)
        result = subprocess.run(
            command,
            cwd=self._project_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=180,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip() or f"SpecBot exited with code {result.returncode}"
            raise RuntimeError(detail)

        payload = self._parse_json_output(result.stdout)
        return {
            "query": cleaned_query,
            "settings": effective,
            "hits": self._extract_hits(payload),
            "rawResult": payload,
            "command": self._display_command(cleaned_query, effective),
        }

    def _merge_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        defaults = self._defaults.to_dict()
        merged = {**defaults, **{key: value for key, value in settings.items() if value is not None}}
        merged["limit"] = max(1, int(merged["limit"]))
        merged["iterations"] = max(1, int(merged["iterations"]))
        merged["nextIterationLimit"] = max(1, int(merged["nextIterationLimit"]))
        merged["followupMode"] = str(merged.get("followupMode") or self._defaults.followup_mode).strip() or self._defaults.followup_mode
        merged["sparseBoost"] = float(merged["sparseBoost"])
        merged["vectorBoost"] = float(merged["vectorBoost"])
        return merged

    def _build_command(self, query: str, settings: dict[str, Any]) -> list[str]:
        command = [
            sys.executable,
            "-m",
            "app.main",
            "iterative-query-vespa-http",
            "--query",
            query,
            "--base-url",
            str(settings["baseUrl"]),
            "--limit",
            str(settings["limit"]),
            "--iterations",
            str(settings["iterations"]),
            "--next-iteration-limit",
            str(settings["nextIterationLimit"]),
            "--followup-mode",
            str(settings["followupMode"]),
            "--summary",
            str(settings["summary"]),
            "--registry",
            str(settings["registry"]),
            "--local-model-dir",
            str(settings["localModelDir"]),
            "--device",
            str(settings["device"]),
            "--sparse-boost",
            str(settings["sparseBoost"]),
            "--vector-boost",
            str(settings["vectorBoost"]),
        ]
        if str(settings.get("configBaseUrl", "")).strip():
            command.extend(["--config-base-url", str(settings["configBaseUrl"])])
        return command

    @staticmethod
    def _parse_json_output(stdout: str) -> dict[str, Any]:
        text = stdout.strip()
        if not text:
            raise RuntimeError("SpecBot returned no output.")
        try:
            return dict(json.loads(text))
        except Exception as exc:
            raise RuntimeError(f"SpecBot returned invalid JSON: {exc}") from exc

    @staticmethod
    def _extract_hits(payload: dict[str, Any]) -> list[dict[str, Any]]:
        hits: list[dict[str, Any]] = []
        for item in payload.get("relevant_documents", []) or []:
            texts = item.get("texts") or []
            preview = texts[0][:240] if texts else ""
            hits.append(
                {
                    "specNo": str(item.get("spec_no", "")),
                    "clauseId": str(item.get("clause_id", "")),
                    "parentClauseId": str(item.get("parent_clause_id", "")),
                    "clausePath": [str(part) for part in item.get("clause_path", [])],
                    "textPreview": preview,
                }
            )
        return hits

    def _display_command(self, query: str, settings: dict[str, Any]) -> str:
        return " ".join(
            [
                "python3 -m app.main iterative-query-vespa-http",
                f'--query "{query}"',
                f'--base-url {settings["baseUrl"]}',
                f'--config-base-url {settings["configBaseUrl"]}',
                f'--limit {settings["limit"]}',
                f'--iterations {settings["iterations"]}',
                f'--next-iteration-limit {settings["nextIterationLimit"]}',
                f'--followup-mode {settings["followupMode"]}',
                f'--summary {settings["summary"]}',
                f'--registry {settings["registry"]}',
                f'--local-model-dir {settings["localModelDir"]}',
                f'--device {settings["device"]}',
                f'--sparse-boost {settings["sparseBoost"]}',
                f'--vector-boost {settings["vectorBoost"]}',
            ]
        )


class SpecbotQueryHttpService:
    def __init__(self, base_url: str, defaults: SpecbotQueryDefaults | None = None, timeout_seconds: float = 180.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._defaults = defaults or SpecbotQueryDefaults()
        self._timeout_seconds = timeout_seconds

    @property
    def defaults(self) -> SpecbotQueryDefaults:
        return self._defaults

    def run(
        self,
        query: str,
        settings: dict[str, Any] | None = None,
        exclude_specs: list[str] | None = None,
        exclude_clauses: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        payload = json.dumps(
            {
                "query": query,
                "settings": settings or self._defaults.to_dict(),
                "excludeSpecs": exclude_specs or [],
                "excludeClauses": exclude_clauses or [],
            },
            ensure_ascii=True,
        ).encode("utf-8")
        request = urllib_request.Request(
            url=f"{self._base_url}/query",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib_request.urlopen(request, timeout=self._timeout_seconds) as response:
                body = response.read().decode("utf-8")
        except urllib_error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(_extract_error_detail(detail) or f"Query API HTTP {exc.code}") from exc
        except urllib_error.URLError as exc:
            raise RuntimeError(f"Unable to reach SpecBot query API at {self._base_url}: {exc.reason}") from exc

        try:
            return dict(json.loads(body))
        except Exception as exc:
            raise RuntimeError(f"SpecBot query API returned invalid JSON: {exc}") from exc

    async def run_async(
        self,
        query: str,
        settings: dict[str, Any] | None = None,
        exclude_specs: list[str] | None = None,
        exclude_clauses: list[dict[str, Any]] | None = None,
        should_cancel=None,
    ) -> dict[str, Any]:
        import httpx

        payload = {
            "query": query,
            "settings": settings or self._defaults.to_dict(),
            "excludeSpecs": exclude_specs or [],
            "excludeClauses": exclude_clauses or [],
        }

        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            request_task = asyncio.create_task(client.post(f"{self._base_url}/query", json=payload))
            try:
                while True:
                    if should_cancel and should_cancel():
                        request_task.cancel()
                        raise RuntimeError("SpecBot query cancelled by client.")
                    if request_task.done():
                        break
                    await asyncio.sleep(0.2)
                response = await request_task
            except asyncio.CancelledError as exc:
                request_task.cancel()
                raise RuntimeError("SpecBot query cancelled by client.") from exc
            except httpx.HTTPError as exc:
                raise RuntimeError(f"Unable to reach SpecBot query API at {self._base_url}: {exc}") from exc

        if response.status_code >= 400:
            raise RuntimeError(_extract_error_detail(response.text) or f"Query API HTTP {response.status_code}")

        try:
            return dict(response.json())
        except Exception as exc:
            raise RuntimeError(f"SpecBot query API returned invalid JSON: {exc}") from exc


def _extract_error_detail(payload_text: str) -> str:
    text = (payload_text or "").strip()
    if not text:
        return ""
    try:
        payload = json.loads(text)
    except Exception:
        return text
    return _stringify_error_detail(payload)


def _stringify_error_detail(value: Any) -> str:
    if isinstance(value, dict):
        if "detail" in value:
            return _stringify_error_detail(value["detail"])
        if "message" in value:
            return _stringify_error_detail(value["message"])
        parts = [f"{key}: {_stringify_error_detail(item)}" for key, item in value.items()]
        return "; ".join(part for part in parts if part)
    if isinstance(value, list):
        parts = [_stringify_error_detail(item) for item in value]
        return "; ".join(part for part in parts if part)
    if value is None:
        return ""
    return str(value)
