from __future__ import annotations

import logging
import os
import re
import inspect
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

from parser.models import DocRecord
from retrieval.anchor_normalizer import is_noisy_anchor, normalize_anchor
from retrieval.multi_hop_pipeline import MultiHopSearchHit
from pydantic import BaseModel, Field


DEFAULT_STAGE_BUCKETS = ["stage2", "stage3", "else"]
DEFAULT_KEYWORD_LIMIT = 5
PROJECT_ROOT = Path(__file__).resolve().parent.parent
RELEVANCE_SYSTEM_PROMPT_PATH = PROJECT_ROOT / "system_prompt_relevance.txt"
RELEVANCE_USER_PROMPT_PATH = PROJECT_ROOT / "user_prompt_relevance.txt"
FEATURE_SYSTEM_PROMPT_PATH = PROJECT_ROOT / "system_prompt_feature_anchor.txt"
FEATURE_USER_PROMPT_PATH = PROJECT_ROOT / "user_propt_feature_anchor.txt"
FOLLOWUP_SYSTEM_PROMPT_PATH = PROJECT_ROOT / "system_prompt_followup_summary.txt"
FOLLOWUP_USER_PROMPT_PATH = PROJECT_ROOT / "user_prompt_followup_summary.txt"
KEYWORD_EXCLUSION_PATH = PROJECT_ROOT / "retrieval" / "keyword_exclusions.txt"
CLAUSE_ONLY_PATTERN = re.compile(r"^(?:clause\s+)?(?P<clause>\d+(?:\.\d+)+(?:[A-Za-z])?)$", re.IGNORECASE)
CLAUSE_SPEC_PATTERN = re.compile(
    r"(?:clause\s+)?(?P<clause>\d+(?:\.\d+)+(?:[A-Za-z])?)\s*(?:of|in)?\s*(?:3gpp\s+)?(?:(?:TS|TR)\s*)?(?P<spec>\d{2}\.\d{3}|\d{5})",
    re.IGNORECASE,
)
logger = logging.getLogger(__name__)


class RetrievalCancelledError(RuntimeError):
    """Raised when an iterative retrieval request is cancelled by the client."""

GENERIC_NEXT_HOP_CLAUSE_TITLES = {
    "general",
    "overview",
    "introduction",
    "references",
    "successful operation",
    "feature negotiation",
    "resource definition",
}

class RelevanceDecision(BaseModel):
    doc_id: str
    is_relevant: bool
    reason: str = ""

class KeywordExtraction(BaseModel):
    doc_id: str
    keywords: list[str] = Field(default_factory=list)
    reason: str = ""

class SummaryDecision(BaseModel):
    doc_id: str
    summary_sentences: list[str] = Field(default_factory=list)
    reason: str = ""


class SummaryDecisionBatch(BaseModel):
    results: list[SummaryDecision] = Field(default_factory=list)


class StageSearchBackend(Protocol):
    def search(
        self,
        terms: list[str],
        limit: int = 20,
        stage_filters: list[str] | None = None,
        spec_filters: list[str] | None = None,
    ) -> list[MultiHopSearchHit]:
        ...


class CandidateEvaluator(Protocol):
    def judge_relevance(self, query_text: str, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        ...

    def extract_keywords(
        self,
        query_text: str,
        relevant_candidates: list[dict[str, Any]],
        keyword_limit: int = 5,
    ) -> list[dict[str, Any]]:
        ...


def _record_context(doc: DocRecord, max_text_chars: int = 1200) -> str:
    parts = [
        doc.spec_title,
        doc.clause_title,
        doc.table_title,
        doc.row_header,
        doc.summary,
        doc.text[:max_text_chars],
    ]
    return "\n".join(part.strip() for part in parts if part and part.strip())


def _doc_content_text(doc: DocRecord, max_text_chars: int = 1200) -> str:
    parts = [
        doc.summary,
        doc.text[:max_text_chars],
        doc.table_markdown,
        " ".join(doc.row_cells),
    ]
    return "\n".join(part.strip() for part in parts if part and part.strip())


def _normalize_keywords(values: list[str], limit: int) -> list[str]:
    keywords: list[str] = []
    seen: set[str] = set()
    for value in values:
        candidate = " ".join(str(value).strip().split())
        if not candidate:
            continue
        key = candidate.lower()
        if key in seen:
            continue
        seen.add(key)
        keywords.append(candidate)
        if len(keywords) >= limit:
            break
    return keywords


def _normalize_search_term(value: str) -> str:
    return " ".join(str(value).strip().lower().split())


def _normalize_spec_no(value: str) -> str:
    return str(value).replace(".", "").strip()


def _content_fingerprint(value: str) -> str:
    return " ".join(str(value).strip().lower().split())


def _read_prompt(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def _render_prompt(path: Path, **values: Any) -> str:
    return _read_prompt(path).format(**values)


def _parse_clause_reference(keyword: str, current_spec_no: str) -> tuple[str, str] | None:
    raw = " ".join(str(keyword).strip().split())
    if not raw:
        return None
    spec_match = CLAUSE_SPEC_PATTERN.search(raw)
    if spec_match:
        return _normalize_spec_no(spec_match.group("spec")), spec_match.group("clause")
    clause_match = CLAUSE_ONLY_PATTERN.match(raw)
    if clause_match and current_spec_no:
        return _normalize_spec_no(current_spec_no), clause_match.group("clause")
    return None


def _should_include_clause_title_as_next_hop(clause_title: str) -> bool:
    normalized_title = normalize_anchor(clause_title).lower()
    if not normalized_title:
        return False
    if is_noisy_anchor(normalized_title):
        return False
    return normalized_title not in GENERIC_NEXT_HOP_CLAUSE_TITLES


@dataclass
class ChatOpenAIRelevanceJudge:
    model: str = "gpt-4o-mini"
    temperature: float = 0.0
    timeout: int = 30
    api_key: str | None = None
    extraction_mode: str = "keyword"
    relevance_system_prompt_path: Path = RELEVANCE_SYSTEM_PROMPT_PATH
    relevance_user_prompt_path: Path = RELEVANCE_USER_PROMPT_PATH
    feature_system_prompt_path: Path = FEATURE_SYSTEM_PROMPT_PATH
    feature_user_prompt_path: Path = FEATURE_USER_PROMPT_PATH
    followup_system_prompt_path: Path = FOLLOWUP_SYSTEM_PROMPT_PATH
    followup_user_prompt_path: Path = FOLLOWUP_USER_PROMPT_PATH
    _llm: Any | None = None
    _relevance_llm: Any | None = None
    _keyword_llm: Any | None = None
    _summary_llm: Any | None = None

    def __post_init__(self) -> None:
        try:
            from langchain_openai import ChatOpenAI
        except ImportError as exc:
            raise RuntimeError(
                "langchain-openai is required for ChatOpenAIRelevanceJudge. Install it with `pip install langchain-openai`."
            ) from exc
        api_key = (self.api_key or os.getenv("OPENAI_API_KEY", "")).strip()
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is required for iterative LLM retrieval.")
        if self.extraction_mode not in {"keyword", "sentence-summary"}:
            raise RuntimeError(f"Unsupported extraction mode: {self.extraction_mode}")
        self._llm = ChatOpenAI(model=self.model, temperature=self.temperature, timeout=self.timeout, api_key=api_key)
        self._relevance_llm = self._llm.with_structured_output(RelevanceDecision, method="json_schema")
        self._keyword_llm = self._llm.with_structured_output(KeywordExtraction, method="json_schema")
        self._summary_llm = self._llm.with_structured_output(SummaryDecision, method="json_schema")

    def judge_relevance(self, query_text: str, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return self._judge_relevance(query_text, candidates, should_cancel=None)

    def _judge_relevance(
        self,
        query_text: str,
        candidates: list[dict[str, Any]],
        should_cancel: Callable[[], bool] | None,
    ) -> list[dict[str, Any]]:
        if not candidates:
            logger.debug("LLM relevance check skipped because there are no candidates for query=%r", query_text)
            return []
        logger.debug(
            "LLM relevance check start query=%r candidate_count=%d candidate_ids=%s",
            query_text,
            len(candidates),
            [str(item.get("doc_id", "")) for item in candidates],
        )
        ordered: list[dict[str, Any]] = []
        for candidate in candidates:
            if should_cancel and should_cancel():
                raise RetrievalCancelledError("Retrieval cancelled by client.")
            prompt_messages = [
                ("system", _read_prompt(self.relevance_system_prompt_path)),
                (
                    "human",
                    _render_prompt(
                        self.relevance_user_prompt_path,
                        query_text=query_text,
                        current_search_term=str(candidate.get("search_term", query_text)),
                        doc_id=str(candidate.get("doc_id", "")),
                        title=str(candidate.get("clause_title") or candidate.get("title") or ""),
                        context_text=str(candidate.get("context", "")),
                    ),
                ),
            ]
            try:
                response = self._relevance_llm.invoke(prompt_messages)
            except Exception as exc:
                raise RuntimeError(
                    f"ChatOpenAI relevance judgement failed for query '{query_text}' and doc '{candidate.get('doc_id', '')}': {exc}"
                ) from exc
            candidate_doc_id = str(candidate.get("doc_id", "")).strip()
            response_doc_id = str(response.doc_id).strip()
            if response_doc_id != candidate_doc_id:
                response_doc_id = candidate_doc_id
            ordered.append(
                {
                    "doc_id": response_doc_id,
                    "is_relevant": bool(response.is_relevant),
                    "keywords": [],
                    "reason": str(response.reason).strip(),
                }
            )
        logger.debug(
            "LLM relevance check complete query=%r relevant=%d/%d",
            query_text,
            sum(1 for item in ordered if item["is_relevant"]),
            len(ordered),
        )
        return ordered

    def extract_keywords(
        self,
        query_text: str,
        relevant_candidates: list[dict[str, Any]],
        keyword_limit: int = DEFAULT_KEYWORD_LIMIT,
    ) -> list[dict[str, Any]]:
        return self._extract_keywords(query_text, relevant_candidates, keyword_limit=keyword_limit, should_cancel=None)

    def _extract_keywords(
        self,
        query_text: str,
        relevant_candidates: list[dict[str, Any]],
        keyword_limit: int = DEFAULT_KEYWORD_LIMIT,
        should_cancel: Callable[[], bool] | None = None,
    ) -> list[dict[str, Any]]:
        if not relevant_candidates:
            logger.debug("LLM keyword extraction skipped because there are no relevant candidates for query=%r", query_text)
            return []
        logger.debug(
            "LLM keyword extraction start query=%r candidate_count=%d candidate_ids=%s",
            query_text,
            len(relevant_candidates),
            [str(item.get("doc_id", "")) for item in relevant_candidates],
        )
        extracted: list[dict[str, Any]] = []
        for candidate in relevant_candidates:
            if should_cancel and should_cancel():
                raise RetrievalCancelledError("Retrieval cancelled by client.")
            system_prompt_path, user_prompt_path = self._followup_prompt_paths()
            followup_label = "Keyword limit" if self.extraction_mode == "keyword" else "Follow-up sentence limit"
            prompt_messages = [
                ("system", _read_prompt(system_prompt_path)),
                (
                    "human",
                    _render_prompt(
                        user_prompt_path,
                        query_text=query_text,
                        keyword_limit=keyword_limit,
                        followup_limit=keyword_limit,
                        followup_label=followup_label,
                        doc_id=str(candidate.get("doc_id", "")),
                        title=str(candidate.get("clause_title") or candidate.get("title") or ""),
                        context_text=str(candidate.get("context", "")),
                    ),
                ),
            ]
            try:
                response = self._followup_llm().invoke(prompt_messages)
            except Exception as exc:
                raise RuntimeError(
                    f"ChatOpenAI keyword extraction failed for query '{query_text}' and doc '{candidate.get('doc_id', '')}': {exc}"
                ) from exc
            candidate_doc_id = str(candidate.get("doc_id", "")).strip()
            response_doc_id = str(response.doc_id).strip()
            if response_doc_id != candidate_doc_id:
                response_doc_id = candidate_doc_id
            extracted_values = (
                response.summary_sentences
                if getattr(self, "extraction_mode", "keyword") == "sentence-summary"
                else response.keywords
            )
            extracted.append(
                {
                    "doc_id": response_doc_id,
                    "keywords": _normalize_keywords(extracted_values, keyword_limit),
                    "reason": str(response.reason).strip(),
                }
            )
        logger.debug(
            "LLM keyword extraction complete query=%r keywords=%s",
            query_text,
            {item["doc_id"]: item["keywords"] for item in extracted},
        )
        return extracted

    def _followup_prompt_paths(self) -> tuple[Path, Path]:
        extraction_mode = getattr(self, "extraction_mode", "keyword")
        if extraction_mode == "sentence-summary":
            return (
                getattr(self, "followup_system_prompt_path", FOLLOWUP_SYSTEM_PROMPT_PATH),
                getattr(self, "followup_user_prompt_path", FOLLOWUP_USER_PROMPT_PATH),
            )
        return (
            getattr(self, "feature_system_prompt_path", FEATURE_SYSTEM_PROMPT_PATH),
            getattr(self, "feature_user_prompt_path", FEATURE_USER_PROMPT_PATH),
        )

    def _followup_llm(self) -> Any:
        if getattr(self, "extraction_mode", "keyword") == "sentence-summary":
            return getattr(self, "_summary_llm", None)
        return getattr(self, "_keyword_llm", None)


@dataclass
class IterativeLLMRetriever:
    backend: StageSearchBackend
    evaluator: CandidateEvaluator
    stage_buckets: list[str] | None = None
    keyword_limit: int = DEFAULT_KEYWORD_LIMIT
    keyword_exclusion_path: Path = KEYWORD_EXCLUSION_PATH
    _excluded_keywords: set[str] = field(init=False, default_factory=set)

    def run(
        self,
        query_text: str,
        limit: int = 4,
        iterations: int = 1,
        next_iteration_limit: int = 2,
        should_cancel: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        self._excluded_keywords = self._load_excluded_keywords()
        active_stages = self.stage_buckets or list(DEFAULT_STAGE_BUCKETS)
        all_results: list[dict[str, Any]] = []
        iteration_results: list[dict[str, Any]] = []
        search_terms = [query_text]
        seen_search_terms = {_normalize_search_term(query_text)}
        pending_clause_targets: list[dict[str, str]] = []
        seen_clause_targets: set[tuple[str, str]] = set()
        seen_doc_ids: set[str] = set()
        seen_content_fingerprints: set[str] = set()
        keyword_extracted_doc_ids: set[str] = set()
        keyword_extracted_content_fingerprints: set[str] = set()
        max_iterations = max(1, iterations)
        logger.debug(
            "Iterative retrieval start query=%r iterations=%d limit=%d next_iteration_limit=%d stages=%s",
            query_text,
            max_iterations,
            limit,
            next_iteration_limit,
            active_stages,
        )

        for iteration_index in range(max_iterations):
            self._check_cancelled(should_cancel)
            iteration_limit = limit if iteration_index == 0 else next_iteration_limit
            logger.debug(
                "Iteration %d start query=%r search_terms=%s limit=%d",
                iteration_index + 1,
                query_text,
                search_terms,
                iteration_limit,
            )
            hits = [
                *self._search_iteration(search_terms, active_stages, iteration_limit, should_cancel=should_cancel),
                *self._resolve_clause_targets(pending_clause_targets, iteration_limit, should_cancel=should_cancel),
            ]
            pending_clause_targets = []
            if not hits:
                logger.debug("Iteration %d produced no hits; stopping", iteration_index + 1)
                break
            deduped_hits_by_content: dict[str, dict[str, Any]] = {}
            for item in hits:
                content_key = _content_fingerprint(_doc_content_text(item["doc"]))
                existing = deduped_hits_by_content.get(content_key)
                if existing is None or float(item["score"]) > float(existing["score"]):
                    deduped_hits_by_content[content_key] = item
            deduped_hits = sorted(
                deduped_hits_by_content.values(),
                key=lambda item: (-float(item["score"]), item["doc"].doc_id),
            )
            deduped_hits_by_doc: dict[str, dict[str, Any]] = {}
            for item in deduped_hits:
                doc_id = item["doc"].doc_id
                existing = deduped_hits_by_doc.get(doc_id)
                if existing is None or float(item["score"]) > float(existing["score"]):
                    deduped_hits_by_doc[doc_id] = item
            unseen_hits = [
                item
                for item in deduped_hits_by_doc.values()
                if item["doc"].doc_id not in seen_doc_ids
                and _content_fingerprint(_doc_content_text(item["doc"])) not in seen_content_fingerprints
            ]
            logger.debug(
                "Iteration %d deduped_hit_count=%d deduped_doc_count=%d unseen_hit_count=%d skipped_seen_doc_count=%d",
                iteration_index + 1,
                len(deduped_hits),
                len(deduped_hits_by_doc),
                len(unseen_hits),
                len(deduped_hits_by_doc) - len(unseen_hits),
            )
            if not unseen_hits:
                logger.debug("Iteration %d only produced already-seen docs; stopping", iteration_index + 1)
                break
            candidates = [self._candidate_payload(item) for item in unseen_hits]
            self._check_cancelled(should_cancel)
            relevances = self._call_evaluator(
                "judge_relevance",
                query_text,
                candidates,
                should_cancel=should_cancel,
            )
            seen_doc_ids.update(candidate["doc_id"] for candidate in candidates)
            seen_content_fingerprints.update(str(candidate["content_fingerprint"]) for candidate in candidates)
            relevant_doc_ids = {
                item["doc_id"] for item in relevances if item["is_relevant"]
            }
            is_last_iteration = iteration_index == max_iterations - 1
            keyword_candidates: list[dict[str, Any]] = []
            extracted_keywords: list[dict[str, Any]] = []
            if is_last_iteration:
                logger.debug("Iteration %d is the last iteration; skipping follow-up extraction", iteration_index + 1)
            else:
                keyword_candidates = [
                    candidate
                    for candidate in candidates
                    if candidate["doc_id"] in relevant_doc_ids and candidate["doc_id"] not in keyword_extracted_doc_ids
                    and str(candidate["content_fingerprint"]) not in keyword_extracted_content_fingerprints
                ]
                self._check_cancelled(should_cancel)
                extracted_keywords = self._call_evaluator(
                    "extract_keywords",
                    query_text,
                    keyword_candidates,
                    keyword_limit=self.keyword_limit,
                    should_cancel=should_cancel,
                )
                keyword_extracted_doc_ids.update(candidate["doc_id"] for candidate in keyword_candidates)
                keyword_extracted_content_fingerprints.update(
                    str(candidate["content_fingerprint"]) for candidate in keyword_candidates
                )
            judgements = self._merge_evaluation_results(relevances, extracted_keywords)
            judged_hits = self._attach_judgements(unseen_hits, judgements)
            next_terms, pending_clause_targets = self._collect_next_actions(
                judged_hits,
                seen_search_terms,
                seen_clause_targets,
            )
            seen_search_terms.update(_normalize_search_term(term) for term in next_terms)
            seen_clause_targets.update((item["spec_no"], item["clause_id"]) for item in pending_clause_targets)
            logger.debug(
                "Iteration %d complete hit_count=%d relevant_count=%d next_terms=%s clause_targets=%s",
                iteration_index + 1,
                len(judged_hits),
                sum(1 for item in judged_hits if item["judgement"]["is_relevant"]),
                next_terms,
                pending_clause_targets,
            )
            payload = {
                "iteration": iteration_index + 1,
                "search_terms": list(search_terms),
                "results": judged_hits,
                "next_search_terms": next_terms,
                "next_clause_targets": pending_clause_targets,
            }
            iteration_results.append(payload)
            all_results.extend(judged_hits)
            if not next_terms and not pending_clause_targets:
                logger.debug("Iteration %d has no next actions; stopping", iteration_index + 1)
                break
            search_terms = next_terms

        logger.debug(
            "Iterative retrieval complete query=%r total_iterations=%d total_results=%d",
            query_text,
            len(iteration_results),
            len(all_results),
        )
        relevant_documents = self._extract_relevant_documents(all_results)
        collected_keywords = self._extract_collected_keywords(all_results)
        return {
            "query": query_text,
            "iterations_requested": max_iterations,
            "iterations": iteration_results,
            "all_results": all_results,
            "relevant_documents": relevant_documents,
            "collected_keywords": collected_keywords,
        }

    def _search_iteration(
        self,
        search_terms: list[str],
        stage_buckets: list[str],
        limit: int,
        should_cancel: Callable[[], bool] | None = None,
    ) -> list[dict[str, Any]]:
        aggregated: dict[tuple[str, str, str], dict[str, Any]] = {}
        for search_term in search_terms:
            for stage_bucket in stage_buckets:
                self._check_cancelled(should_cancel)
                logger.debug(
                    "Searching Vespa search_term=%r stage_bucket=%s limit=%d",
                    search_term,
                    stage_bucket,
                    limit,
                )
                hits = self.backend.search([search_term], limit=limit, stage_filters=[stage_bucket])
                logger.debug(
                    "Search complete search_term=%r stage_bucket=%s hit_count=%d doc_ids=%s",
                    search_term,
                    stage_bucket,
                    len(hits),
                    [hit.doc.doc_id for hit in hits],
                )
                for hit in hits:
                    key = (search_term, stage_bucket, hit.doc.doc_id)
                    payload = {
                        "iteration_search_term": search_term,
                        "stage_bucket": stage_bucket,
                        "score": hit.score,
                        "reason_type": hit.reason_type,
                        "matched_text": hit.matched_text,
                        "doc": hit.doc,
                    }
                    existing = aggregated.get(key)
                    if existing is None or float(payload["score"]) > float(existing["score"]):
                        aggregated[key] = payload
        return sorted(
            aggregated.values(),
            key=lambda item: (-float(item["score"]), item["doc"].doc_id),
        )

    def _candidate_payload(self, item: dict[str, Any]) -> dict[str, Any]:
        doc = item["doc"]
        return {
            "doc_id": doc.doc_id,
            "search_term": item["iteration_search_term"],
            "stage_bucket": item["stage_bucket"],
            "spec_no": doc.spec_no,
            "clause_id": doc.clause_id,
            "parent_clause_id": doc.parent_clause_id,
            "clause_path": list(doc.clause_path),
            "clause_title": doc.clause_title,
            "score": item["score"],
            "context": _record_context(doc),
            "content_fingerprint": _content_fingerprint(_doc_content_text(doc)),
        }

    def _attach_judgements(self, hits: list[dict[str, Any]], judgements: list[dict[str, Any]]) -> list[dict[str, Any]]:
        judgements_by_id = {str(item["doc_id"]): item for item in judgements}
        results: list[dict[str, Any]] = []
        for item in hits:
            doc = item["doc"]
            judgement = judgements_by_id.get(doc.doc_id, {"doc_id": doc.doc_id, "is_relevant": False, "keywords": [], "reason": ""})
            results.append(
                {
                    "doc_id": doc.doc_id,
                    "spec_no": doc.spec_no,
                    "stage_hint": doc.stage_hint or item["stage_bucket"],
                    "clause_id": doc.clause_id,
                    "parent_clause_id": doc.parent_clause_id,
                    "clause_path": list(doc.clause_path),
                    "clause_title": doc.clause_title,
                    "search_term": item["iteration_search_term"],
                    "stage_bucket": item["stage_bucket"],
                    "score": item["score"],
                    "reason_type": item["reason_type"],
                    "matched_text": item["matched_text"],
                    "summary": doc.summary,
                    "text": doc.text,
                    "judgement": judgement,
                }
            )
        return results

    def _merge_evaluation_results(
        self,
        relevances: list[dict[str, Any]],
        extracted_keywords: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        keywords_by_id = {str(item["doc_id"]): item for item in extracted_keywords}
        merged: list[dict[str, Any]] = []
        for item in relevances:
            doc_id = str(item["doc_id"])
            keyword_item = keywords_by_id.get(doc_id, {})
            merged.append(
                {
                    "doc_id": doc_id,
                    "is_relevant": bool(item.get("is_relevant")),
                    "keywords": self._filter_keywords(
                        _normalize_keywords(
                            keyword_item.get("keywords", []) if item.get("is_relevant") else [],
                            self.keyword_limit,
                        )
                    ),
                    "reason": str(item.get("reason", "")).strip(),
                    "keyword_reason": str(keyword_item.get("reason", "")).strip(),
                }
            )
        return merged

    def _collect_next_actions(
        self,
        judged_hits: list[dict[str, Any]],
        seen_search_terms: set[str],
        seen_clause_targets: set[tuple[str, str]],
    ) -> tuple[list[str], list[dict[str, str]]]:
        next_terms: list[str] = []
        clause_targets: list[dict[str, str]] = []
        seen_local_clause_targets: set[tuple[str, str]] = set()
        keyword_buffer: list[str] = []
        clause_title_buffer: list[str] = []
        seen_clause_titles: set[str] = set()
        for item in judged_hits:
            judgement = item["judgement"]
            if not judgement.get("is_relevant"):
                continue
            clause_title = " ".join(str(item.get("clause_title", "")).strip().split())
            normalized_clause_title = _normalize_search_term(clause_title)
            if (
                clause_title
                and normalized_clause_title
                and normalized_clause_title not in seen_clause_titles
                and _should_include_clause_title_as_next_hop(clause_title)
            ):
                seen_clause_titles.add(normalized_clause_title)
                clause_title_buffer.append(clause_title)
            for keyword in judgement.get("keywords", []):
                clause_reference = _parse_clause_reference(keyword, item.get("spec_no", ""))
                if clause_reference is not None:
                    target_key = clause_reference
                    if target_key in seen_clause_targets or target_key in seen_local_clause_targets:
                        continue
                    seen_local_clause_targets.add(target_key)
                    clause_targets.append({"spec_no": target_key[0], "clause_id": target_key[1]})
                    continue
                keyword_buffer.append(keyword)
        next_terms = [
            keyword
            for keyword in _normalize_keywords([*keyword_buffer, *clause_title_buffer], limit=self.keyword_limit * 6)
            if _normalize_search_term(keyword) not in seen_search_terms
        ][: self.keyword_limit * 2]
        logger.debug("Collected next search terms=%s clause_targets=%s", next_terms, clause_targets)
        return next_terms, clause_targets

    def _resolve_clause_targets(
        self,
        clause_targets: list[dict[str, str]],
        limit: int,
        should_cancel: Callable[[], bool] | None = None,
    ) -> list[dict[str, Any]]:
        if not clause_targets:
            return []
        lookup_clause = getattr(self.backend, "lookup_clause", None)
        if lookup_clause is None:
            logger.debug("Clause target resolution skipped because backend does not support lookup_clause")
            return []
        resolved: list[dict[str, Any]] = []
        for target in clause_targets:
            self._check_cancelled(should_cancel)
            hits = lookup_clause(target["spec_no"], target["clause_id"], limit=limit)
            logger.debug("Resolved clause target spec_no=%s clause_id=%s hit_count=%d", target["spec_no"], target["clause_id"], len(hits))
            for hit in hits:
                resolved.append(
                    {
                        "iteration_search_term": f'{target["clause_id"]} of {target["spec_no"]}',
                        "stage_bucket": hit.doc.stage_hint or "",
                        "score": hit.score,
                        "reason_type": hit.reason_type,
                        "matched_text": hit.matched_text,
                        "doc": hit.doc,
                    }
                )
        return resolved

    def _extract_relevant_documents(self, all_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        extracted_by_key: dict[tuple[str, str], dict[str, Any]] = {}
        for item in all_results:
            judgement = item.get("judgement", {})
            if not judgement.get("is_relevant"):
                continue
            spec_no = str(item.get("spec_no", ""))
            clause_id = str(item.get("clause_id", ""))
            dedupe_key = (spec_no, clause_id)
            text = str(item.get("text", "")).strip()
            existing = extracted_by_key.get(dedupe_key)
            if existing is None:
                texts = [text] if text else []
                extracted_by_key[dedupe_key] = {
                    "doc_id": str(item.get("doc_id", "")),
                    "spec_no": spec_no,
                    "clause_id": clause_id,
                    "parent_clause_id": str(item.get("parent_clause_id", "")),
                    "clause_path": list(item.get("clause_path", [])),
                    "texts": texts,
                }
                continue
            if text and text not in existing["texts"]:
                existing["texts"] = [*existing["texts"], text]
        return list(extracted_by_key.values())

    def _extract_collected_keywords(self, all_results: list[dict[str, Any]]) -> list[str]:
        keywords: list[str] = []
        seen: set[str] = set()
        for item in all_results:
            for keyword in item.get("judgement", {}).get("keywords", []):
                normalized = _normalize_search_term(keyword)
                if not normalized or normalized in seen:
                    continue
                seen.add(normalized)
                keywords.append(str(keyword))
        return keywords

    def _load_excluded_keywords(self) -> set[str]:
        if not self.keyword_exclusion_path.exists():
            logger.debug("Keyword exclusion file not found: %s", self.keyword_exclusion_path)
            return set()
        excluded: set[str] = set()
        for raw_line in self.keyword_exclusion_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            normalized = _normalize_search_term(line)
            if normalized:
                excluded.add(normalized)
        logger.debug("Loaded %d excluded keywords from %s", len(excluded), self.keyword_exclusion_path)
        return excluded

    def _filter_keywords(self, keywords: list[str]) -> list[str]:
        if not self._excluded_keywords:
            return keywords
        return [
            keyword
            for keyword in keywords
            if _normalize_search_term(keyword) not in self._excluded_keywords
        ]

    @staticmethod
    def _check_cancelled(should_cancel: Callable[[], bool] | None) -> None:
        if should_cancel and should_cancel():
            raise RetrievalCancelledError("Retrieval cancelled by client.")

    def _call_evaluator(self, method_name: str, *args: Any, should_cancel: Callable[[], bool] | None = None, **kwargs: Any):
        method = getattr(self.evaluator, method_name)
        try:
            signature = inspect.signature(method)
        except (TypeError, ValueError):
            signature = None
        if signature and "should_cancel" in signature.parameters:
            return method(*args, should_cancel=should_cancel, **kwargs)
        return method(*args, **kwargs)
