from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol


class SelectionLLM(Protocol):
    def select_specs(self, query_text: str, candidates: list[dict[str, Any]], limit: int = 6) -> list[str]:
        ...

    def judge_relevance(self, query_text: str, candidates: list[dict[str, Any]], limit: int = 6) -> list[str]:
        ...

    def select_anchors(self, query_text: str, candidates: list[dict[str, Any]], limit: int = 6) -> list[str]:
        ...


class HeuristicSelectionLLM:
    def select_specs(self, query_text: str, candidates: list[dict[str, Any]], limit: int = 6) -> list[str]:
        del query_text
        return [str(item["spec_id"]) for item in candidates[:limit] if item.get("spec_id")]

    def judge_relevance(self, query_text: str, candidates: list[dict[str, Any]], limit: int = 6) -> list[str]:
        del query_text
        return [str(item["doc_id"]) for item in candidates[:limit] if item.get("doc_id")]

    def select_anchors(self, query_text: str, candidates: list[dict[str, Any]], limit: int = 6) -> list[str]:
        del query_text
        return [str(item["anchor_id"]) for item in candidates[:limit] if item.get("anchor_id")]


@dataclass
class OpenAISelectionLLM:
    api_key: str
    model: str = "gpt-4o-mini"
    endpoint: str = "https://api.openai.com/v1/responses"
    timeout_seconds: int = 30

    @classmethod
    def from_env(cls, model: str = "gpt-4o-mini") -> OpenAISelectionLLM | None:
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            return None
        return cls(api_key=api_key, model=model)

    def judge_relevance(self, query_text: str, candidates: list[dict[str, Any]], limit: int = 6) -> list[str]:
        allowed_ids = [str(item["doc_id"]) for item in candidates if item.get("doc_id")]
        prompt = {
            "task": "Select relevant clause candidates for a 3GPP retrieval hop.",
            "rules": [
                "Select only doc_id values from the provided candidates.",
                "Do not invent new doc_id values.",
                "Judge relevance from the candidate evidence only; do not prefer or reject a candidate just because it is Stage 2, Stage 3, or else.",
                "Some candidates may appear multiple times with different text_chunk_index values; keep a doc_id if any chunk is relevant.",
                "Prefer title match, IE/message/procedure match, table match, explicit spec reference, and semantic relevance.",
                f"Return at most {limit} doc_id values.",
            ],
            "query": query_text,
            "candidates": candidates,
            "output_schema": {"selected_doc_ids": ["doc_id"]},
        }
        selected_ids = self._request_json(prompt).get("selected_doc_ids", [])
        return [item for item in selected_ids if item in allowed_ids][:limit]

    def select_specs(self, query_text: str, candidates: list[dict[str, Any]], limit: int = 6) -> list[str]:
        allowed_ids = [str(item["spec_id"]) for item in candidates if item.get("spec_id")]
        prompt = {
            "task": "Select specification candidates for the next 3GPP retrieval hop.",
            "rules": [
                "Select only spec_id values from the provided candidates.",
                "Do not invent new spec_id values.",
                "Prefer specs that are likely to contain clauses directly relevant to the query or the next retrieval hop.",
                f"Return at most {limit} spec_id values.",
            ],
            "query": query_text,
            "candidates": candidates,
            "output_schema": {"selected_spec_ids": ["spec_id"]},
        }
        selected_ids = self._request_json(prompt).get("selected_spec_ids", [])
        return [item for item in selected_ids if item in allowed_ids][:limit]

    def select_anchors(self, query_text: str, candidates: list[dict[str, Any]], limit: int = 6) -> list[str]:
        allowed_ids = [str(item["anchor_id"]) for item in candidates if item.get("anchor_id")]
        prompt = {
            "task": "Select anchor candidates for the next 3GPP retrieval hop.",
            "rules": [
                "Select only anchor_id values from the provided candidates.",
                "Do not invent new anchors or rewrite anchor text.",
                "Prefer anchors that are most relevant to the query and most useful for finding related Stage 2, Stage 3, or RAN clauses.",
                f"Return at most {limit} anchor_id values.",
            ],
            "query": query_text,
            "candidates": candidates,
            "output_schema": {"selected_anchor_ids": ["anchor_id"]},
        }
        selected_ids = self._request_json(prompt).get("selected_anchor_ids", [])
        return [item for item in selected_ids if item in allowed_ids][:limit]

    def _request_json(self, prompt: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "input": json.dumps(prompt, ensure_ascii=True),
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "selection_result",
                    "schema": {
                        "type": "object",
                        "properties": {
                            "selected_spec_ids": {"type": "array", "items": {"type": "string"}},
                            "selected_doc_ids": {"type": "array", "items": {"type": "string"}},
                            "selected_anchor_ids": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["selected_spec_ids", "selected_doc_ids", "selected_anchor_ids"],
                        "additionalProperties": False,
                    },
                }
            },
        }
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"OpenAI selection request failed: {exc.code} {body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"OpenAI selection request failed: {exc.reason}") from exc

        text = self._extract_output_text(data)
        if not text:
            return {}
        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            return {}
        return parsed

    @staticmethod
    def _extract_output_text(response: dict[str, Any]) -> str:
        output_text = response.get("output_text")
        if isinstance(output_text, str) and output_text.strip():
            return output_text
        output = response.get("output", [])
        if not isinstance(output, list):
            return ""
        for item in output:
            content = item.get("content", [])
            if not isinstance(content, list):
                continue
            for block in content:
                text = block.get("text")
                if isinstance(text, str) and text.strip():
                    return text
        return ""
