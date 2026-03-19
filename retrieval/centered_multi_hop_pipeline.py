from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from parser.models import DocRecord
from retrieval.anchor_extractor import extract_anchor_candidates
from retrieval.anchor_normalizer import normalize_anchor
from retrieval.anchor_selector import select_anchors
from retrieval.llm_selector import HeuristicSelectionLLM, SelectionLLM
from retrieval.multi_hop_pipeline import (
    GENERIC_QUERY_ANCHOR_TOKENS,
    MultiHopBackend,
    MultiHopSearchHit,
)
from retrieval.query_normalizer import QueryFeatureRegistry, normalize_query
from retrieval.relevance_scorer import score_relevance
from retrieval.relevance_signals import collect_relevance_signals
from retrieval.result_merger import merge_clause_results
from retrieval.stage_router import (
    RoutingIndex,
    build_routing_index,
    build_spec_candidates,
    infer_entry_specs,
    resolve_spec_stage_filters,
    resolve_stage_buckets,
)


def _anchor_query_overlap(anchor: str, query_terms: list[str]) -> int:
    anchor_tokens = {
        token.lower()
        for token in normalize_anchor(anchor).split()
        if token and token.lower() not in GENERIC_QUERY_ANCHOR_TOKENS
    }
    query_token_set = {
        token.lower()
        for term in query_terms
        for token in normalize_anchor(term).split()
        if token and token.lower() not in GENERIC_QUERY_ANCHOR_TOKENS
    }
    return len(anchor_tokens.intersection(query_token_set))


GENERIC_CLAUSE_TITLES = {
    "general",
    "feature negotiation",
    "successful operation",
    "resource definition",
    "references",
    "introduction",
    "overview",
}
MAX_RELEVANCE_TEXT_CHUNK_CHARS = 2000
MAX_RELEVANCE_TEXT_CHUNKS = 3


def _merged_clause_penalty(clause_title: str) -> float:
    lowered = (clause_title or "").strip().lower()
    return 6.0 if lowered in GENERIC_CLAUSE_TITLES else 0.0


def _merged_clause_overlap_bonus(clause_title: str, query_terms: list[str]) -> float:
    normalized_title = normalize_anchor(clause_title)
    if not normalized_title:
        return 0.0
    title_tokens = {
        token.lower()
        for token in normalized_title.split()
        if token and token.lower() not in GENERIC_QUERY_ANCHOR_TOKENS
    }
    query_tokens = {
        token.lower()
        for term in query_terms
        for token in normalize_anchor(term).split()
        if token and token.lower() not in GENERIC_QUERY_ANCHOR_TOKENS
    }
    overlap = len(title_tokens.intersection(query_tokens))
    return 1.2 * overlap


def _build_text_chunks(text: str, chunk_size: int = MAX_RELEVANCE_TEXT_CHUNK_CHARS, max_chunks: int = MAX_RELEVANCE_TEXT_CHUNKS) -> list[str]:
    normalized = (text or "").strip()
    if not normalized:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(normalized) and len(chunks) < max_chunks:
        end = min(start + chunk_size, len(normalized))
        chunks.append(normalized[start:end])
        start = end
    return chunks


@dataclass
class CenteredMultiHopRetrievalPipeline:
    backend: MultiHopBackend
    registry: QueryFeatureRegistry | None = None
    selector: SelectionLLM | None = None
    llm_relevance_only: bool = False

    def __post_init__(self) -> None:
        if self.registry is None:
            self.registry = QueryFeatureRegistry()
        if self.selector is None:
            self.selector = HeuristicSelectionLLM()
        backend_records = getattr(self.backend, "records", [])
        self.routing_index: RoutingIndex = build_routing_index(list(backend_records))

    def run(self, query_text: str, limit: int = 10) -> dict[str, Any]:
        normalized = normalize_query(query_text, registry=self.registry)
        stage_buckets = resolve_stage_buckets(normalized)
        stage_limit = max(1, limit)
        query_terms = [normalized.normalized_query, *normalized.candidate_anchors, *normalized.aliases, *normalized.features.get("tokens", [])]

        initial_hits = self._search_initial_stage_hits(query_terms, stage_buckets, limit=max(limit * 3, 12))
        scored_seed_hits = (
            self._prepare_hits(initial_hits)
            if self.llm_relevance_only
            else self._score_hits(normalized, initial_hits)
        )
        judged_seed_hits = self._judge_hits_by_stage(query_text, scored_seed_hits, stage_buckets, stage_limit=stage_limit)
        seed_docs = [item["doc"] for item in judged_seed_hits[:limit]]
        entry_specs = self._collect_entry_specs(seed_docs, limit=6)
        entry_spec_candidates = self._build_entry_spec_candidates(seed_docs)

        selected_anchors = self._select_anchors(query_text, seed_docs, query_terms, limit=8)
        expansion_spec_candidates = self._build_expansion_spec_candidates(normalized, seed_docs, stage_buckets)
        expansion_specs = self._select_specs(query_text, expansion_spec_candidates, fallback_limit=8)
        expansion_hits = self._search_expansion_hits(selected_anchors, stage_buckets, expansion_specs, limit=max(limit * 2, 12))
        scored_expansion_hits = (
            self._prepare_hits(expansion_hits, reason_type="anchor_hit")
            if self.llm_relevance_only
            else self._score_hits(normalized, expansion_hits, reason_type="anchor_hit")
        )
        judged_expansion_hits = self._judge_hits_by_stage(query_text, scored_expansion_hits, stage_buckets, stage_limit=stage_limit)

        merged_hits = merge_clause_results([*judged_seed_hits, *judged_expansion_hits])
        reranked_hits = self._rerank_merged_clauses(merged_hits, query_terms)
        return {
            "query": normalized,
            "entry_specs": entry_specs,
            "entry_spec_candidates": entry_spec_candidates,
            "stage_buckets": stage_buckets,
            "direct_hits": judged_seed_hits[:limit],
            "selected_anchors": selected_anchors,
            "expansion_specs": expansion_specs,
            "expanded_hits": judged_expansion_hits[: limit * 2],
            "merged_clauses": reranked_hits[:limit],
        }

    def _search_initial_stage_hits(
        self,
        query_terms: list[str],
        stage_buckets: list[str],
        limit: int,
    ) -> list[MultiHopSearchHit]:
        hits: list[MultiHopSearchHit] = []
        for bucket in stage_buckets:
            hits.extend(self.backend.search(query_terms, limit=limit, stage_filters=[bucket]))
        return self._dedupe_hits(hits, limit=limit * max(len(stage_buckets), 1))

    def _search_expansion_hits(
        self,
        selected_anchors: list[dict[str, Any]],
        stage_buckets: list[str],
        expansion_specs: list[str],
        limit: int,
    ) -> list[MultiHopSearchHit]:
        hits: list[MultiHopSearchHit] = []
        for anchor in selected_anchors:
            for spec in expansion_specs:
                spec_stage_filters = resolve_spec_stage_filters(spec, stage_buckets, self.routing_index)
                hits.extend(
                    self.backend.search(
                        [anchor["anchor"]],
                        limit=limit,
                        stage_filters=spec_stage_filters,
                        spec_filters=[spec],
                    )
                )
        return self._dedupe_hits(hits, limit=limit * max(len(expansion_specs), 1))

    def _select_specs(self, query_text: str, candidates: list[dict[str, Any]], fallback_limit: int) -> list[str]:
        if not candidates:
            return []
        selected_spec_ids = self.selector.select_specs(query_text, candidates, limit=min(fallback_limit, len(candidates)))
        if not selected_spec_ids:
            return [str(item["spec_id"]) for item in candidates[:fallback_limit]]
        selected_set = set(selected_spec_ids)
        selected = [str(item["spec_id"]) for item in candidates if item["spec_id"] in selected_set]
        return selected[:fallback_limit] if selected else [str(item["spec_id"]) for item in candidates[:fallback_limit]]

    def _collect_entry_specs(self, seed_docs: list[DocRecord], limit: int) -> list[str]:
        specs: list[str] = []
        for doc in seed_docs:
            if doc.spec_no and doc.spec_no not in specs:
                specs.append(doc.spec_no)
        return specs[:limit]

    def _build_entry_spec_candidates(self, seed_docs: list[DocRecord]) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        for spec_no in self._collect_entry_specs(seed_docs, limit=8):
            candidates.append(
                {
                    "spec_id": spec_no,
                    "spec_no": spec_no,
                    "spec_title": self.routing_index.spec_titles.get(spec_no, ""),
                    "stage_hints": self.routing_index.spec_stage_index.get(spec_no, []),
                    "seed_support": sum(1 for doc in seed_docs if doc.spec_no == spec_no),
                }
            )
        return candidates

    def _build_expansion_spec_candidates(
        self,
        normalized_query,
        seed_docs: list[DocRecord],
        stage_buckets: list[str],
    ) -> list[dict[str, Any]]:
        if not seed_docs:
            return build_spec_candidates(normalized_query, self.routing_index, stage_buckets=stage_buckets, limit=8)
        preferred_specs = [doc.spec_no for doc in seed_docs if doc.spec_no]
        inferred_specs = infer_entry_specs(normalized_query, self.routing_index, stage_buckets=stage_buckets, limit=8)
        ordered_specs: list[str] = []
        for spec_no in [*preferred_specs, *inferred_specs]:
            if spec_no and spec_no not in ordered_specs:
                ordered_specs.append(spec_no)
        candidates: list[dict[str, Any]] = []
        for spec_no in ordered_specs[:8]:
            candidates.append(
                {
                    "spec_id": spec_no,
                    "spec_no": spec_no,
                    "spec_title": self.routing_index.spec_titles.get(spec_no, ""),
                    "stage_hints": self.routing_index.spec_stage_index.get(spec_no, []),
                    "top_terms": list(self.routing_index.spec_term_scores.get(spec_no, {}).keys())[:8],
                    "seed_support": sum(1 for doc in seed_docs if doc.spec_no == spec_no),
                }
            )
        return candidates

    def _rerank_merged_clauses(self, merged_hits: list[dict[str, Any]], query_terms: list[str]) -> list[dict[str, Any]]:
        reranked: list[dict[str, Any]] = []
        for item in merged_hits:
            penalty = _merged_clause_penalty(item.get("clause_title", ""))
            bonus = _merged_clause_overlap_bonus(item.get("clause_title", ""), query_terms)
            adjusted_score = round(float(item.get("score", 0.0)) + bonus - penalty, 3)
            reranked.append(
                {
                    **item,
                    "score": adjusted_score,
                    "ranking_adjustment": {"query_overlap_bonus": bonus, "generic_clause_penalty": penalty},
                }
            )
        return sorted(reranked, key=lambda item: (-item["score"], item["clause_key"]))

    def _prepare_hits(
        self,
        hits: list[MultiHopSearchHit],
        reason_type: str = "direct_hit",
    ) -> list[dict[str, Any]]:
        prepared_hits: list[dict[str, Any]] = []
        for hit in hits:
            prepared_hits.append(
                {
                    "doc": hit.doc,
                    "doc_id": hit.doc.doc_id,
                    "score": round(float(hit.score), 3),
                    "reason_type": reason_type,
                    "matched_text": hit.matched_text,
                    "relevance_breakdown": {"retrieval_score": round(float(hit.score), 3)},
                }
            )
        return sorted(prepared_hits, key=lambda item: (-item["score"], item["doc_id"]))

    def _score_hits(
        self,
        normalized_query,
        hits: list[MultiHopSearchHit],
        reason_type: str = "direct_hit",
    ) -> list[dict[str, Any]]:
        scored_hits: list[dict[str, Any]] = []
        for hit in hits:
            signals = collect_relevance_signals(normalized_query, hit.doc, retrieval_score=hit.score)
            relevance_score, breakdown = score_relevance(signals)
            if relevance_score <= 0:
                continue
            scored_hits.append(
                {
                    "doc": hit.doc,
                    "doc_id": hit.doc.doc_id,
                    "score": relevance_score,
                    "reason_type": reason_type,
                    "matched_text": hit.matched_text,
                    "relevance_breakdown": breakdown,
                }
            )
        return sorted(scored_hits, key=lambda item: (-item["score"], item["doc_id"]))

    def _judge_hits(self, query_text: str, hits: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
        if not hits:
            return []
        candidates = self._build_relevance_candidates(hits[: max(limit * 2, 8)])
        selected_doc_ids = self.selector.judge_relevance(query_text, candidates, limit=limit)
        if not selected_doc_ids:
            return hits[:limit]
        selected_set = set(selected_doc_ids)
        filtered = [item for item in hits if item["doc_id"] in selected_set]
        return filtered[:limit] if filtered else hits[:limit]

    def _build_relevance_candidates(self, hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        for item in hits:
            doc = item["doc"]
            text_chunks = _build_text_chunks(doc.text or doc.embedding_text)
            if not text_chunks:
                text_chunks = [""]
            for chunk_index, text_chunk in enumerate(text_chunks):
                candidates.append(
                    {
                        "doc_id": item["doc_id"],
                        "spec_no": doc.spec_no,
                        "stage_hint": doc.stage_hint,
                        "clause_id": doc.clause_id,
                        "clause_title": doc.clause_title,
                        "doc_type": doc.doc_type,
                        "score": round(float(item["score"]), 3),
                        "signals": item["relevance_breakdown"],
                        "matched_text": item["matched_text"],
                        "text_chunk_index": chunk_index,
                        "text_chunk_count": len(text_chunks),
                        "text_excerpt": text_chunk,
                    }
                )
        return candidates

    def _judge_hits_by_stage(
        self,
        query_text: str,
        hits: list[dict[str, Any]],
        stage_buckets: list[str],
        stage_limit: int,
    ) -> list[dict[str, Any]]:
        grouped: dict[str, list[dict[str, Any]]] = {bucket: [] for bucket in stage_buckets}
        for item in hits:
            stage_hint = item["doc"].stage_hint or "else"
            grouped.setdefault(stage_hint, []).append(item)

        judged: list[dict[str, Any]] = []
        for bucket in stage_buckets:
            stage_hits = grouped.get(bucket, [])
            if not stage_hits:
                continue
            judged.extend(self._judge_hits(query_text, stage_hits, limit=stage_limit))
        return sorted(judged, key=lambda item: (-item["score"], item["doc_id"]))

    def _select_anchors(
        self,
        query_text: str,
        seed_docs: list[DocRecord],
        query_terms: list[str],
        limit: int,
    ) -> list[dict[str, Any]]:
        anchor_candidates = extract_anchor_candidates(seed_docs)
        filtered_candidates: list[dict[str, Any]] = []
        for item in anchor_candidates:
            overlap = _anchor_query_overlap(item["anchor"], query_terms)
            if overlap <= 0 and "clause_title" not in item.get("sources", []):
                continue
            filtered_candidates.append({**item, "query_overlap": overlap})
        ranked_candidates = select_anchors(filtered_candidates, limit=max(limit * 2, 8))
        payload = [
            {
                "anchor_id": f"a{index}",
                "anchor": item["anchor"],
                "sources": item.get("sources", []),
                "score": item["score"],
                "spec_count": item.get("spec_count", 0),
                "doc_count": item.get("doc_count", 0),
            }
            for index, item in enumerate(ranked_candidates)
        ]
        selected_anchor_ids = self.selector.select_anchors(query_text, payload, limit=limit)
        if not selected_anchor_ids:
            return ranked_candidates[:limit]
        selected_set = set(selected_anchor_ids)
        selected = [item for item, payload_item in zip(ranked_candidates, payload, strict=False) if payload_item["anchor_id"] in selected_set]
        return selected[:limit] if selected else ranked_candidates[:limit]

    @staticmethod
    def _dedupe_hits(hits: list[MultiHopSearchHit], limit: int) -> list[MultiHopSearchHit]:
        deduped: dict[str, MultiHopSearchHit] = {}
        for hit in hits:
            existing = deduped.get(hit.doc.doc_id)
            if existing is None or hit.score > existing.score:
                deduped[hit.doc.doc_id] = hit
        return sorted(deduped.values(), key=lambda item: (-item.score, item.doc.doc_id))[:limit]
