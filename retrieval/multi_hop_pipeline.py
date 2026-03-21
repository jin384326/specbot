from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Protocol

from parser.models import DocRecord
from retrieval.anchor_extractor import extract_anchor_candidates
from retrieval.anchor_normalizer import normalize_anchor
from retrieval.anchor_selector import select_anchors
from retrieval.hop_policy import infer_hop_stage_targets
from retrieval.query_normalizer import QueryFeatureRegistry, normalize_query
from retrieval.relevance_scorer import score_relevance
from retrieval.relevance_signals import collect_relevance_signals
from retrieval.result_merger import merge_clause_results

GENERIC_QUERY_ANCHOR_TOKENS = {"message", "messages", "procedure", "procedures", "path", "paths", "end", "request"}


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


@dataclass
class MultiHopSearchHit:
    doc: DocRecord
    score: float
    reason_type: str
    matched_text: str
    metadata: dict


class MultiHopBackend(Protocol):
    def search(
        self,
        terms: Iterable[str],
        limit: int = 20,
        stage_filters: list[str] | None = None,
        spec_filters: list[str] | None = None,
    ) -> list[MultiHopSearchHit]:
        ...

    def lookup_clause(
        self,
        spec_no: str,
        clause_id: str,
        limit: int = 20,
        stage_filters: list[str] | None = None,
    ) -> list[MultiHopSearchHit]:
        ...


class InMemoryMultiHopBackend:
    def __init__(self, records: Iterable[DocRecord]) -> None:
        self.records = list(records)

    def search(
        self,
        terms: Iterable[str],
        limit: int = 20,
        stage_filters: list[str] | None = None,
        spec_filters: list[str] | None = None,
    ) -> list[MultiHopSearchHit]:
        normalized_terms = [term.strip().lower() for term in terms if term and term.strip()]
        hits: list[MultiHopSearchHit] = []
        for record in self.records:
            if stage_filters and record.stage_hint not in stage_filters:
                continue
            if spec_filters and record.spec_no not in spec_filters:
                continue
            score, matched = self._score_record(record, normalized_terms)
            if score <= 0 or not matched:
                continue
            hits.append(
                MultiHopSearchHit(
                    doc=record,
                    score=round(score, 3),
                    reason_type="direct_hit",
                    matched_text=", ".join(matched[:5]),
                    metadata={},
                )
            )
        return sorted(hits, key=lambda item: (-item.score, item.doc.doc_id))[:limit]

    def lookup_clause(
        self,
        spec_no: str,
        clause_id: str,
        limit: int = 20,
        stage_filters: list[str] | None = None,
    ) -> list[MultiHopSearchHit]:
        hits: list[MultiHopSearchHit] = []
        for record in self.records:
            if record.spec_no != spec_no or record.clause_id != clause_id:
                continue
            if stage_filters and record.stage_hint not in stage_filters:
                continue
            hits.append(
                MultiHopSearchHit(
                    doc=record,
                    score=99.0,
                    reason_type="clause_reference",
                    matched_text=clause_id,
                    metadata={"spec_no": spec_no, "clause_id": clause_id},
                )
            )
        return sorted(hits, key=lambda item: item.doc.doc_id)[:limit]

    @staticmethod
    def _score_record(record: DocRecord, normalized_terms: list[str]) -> tuple[float, list[str]]:
        if not normalized_terms:
            return 0.0, []
        clause_title = (record.clause_title or "").lower()
        row_header = (record.row_header or "").lower()
        anchor_terms = " ".join(record.anchor_terms).lower()
        ie_names = " ".join(record.ie_names).lower()
        message_names = " ".join(record.message_names).lower()
        procedure_names = " ".join(record.procedure_names).lower()
        text = (record.embedding_text or record.text or "").lower()
        matched: list[str] = []
        score = 0.0
        for term in normalized_terms:
            if not term:
                continue
            term_score = 0.0
            title_overlap = InMemoryMultiHopBackend._token_overlap_score(term, clause_title)
            if clause_title and term == clause_title:
                term_score = max(term_score, 14.0)
            elif clause_title and len(term) >= 5 and term in clause_title:
                term_score = max(term_score, 8.0)
            elif title_overlap > 0:
                term_score = max(term_score, title_overlap)
            if row_header and len(term) >= 4 and term in row_header:
                term_score = max(term_score, 4.0)
            if ie_names and len(term) >= 4 and term in ie_names:
                term_score = max(term_score, 5.0)
            if message_names and len(term) >= 4 and term in message_names:
                term_score = max(term_score, 5.5)
            if procedure_names and len(term) >= 4 and term in procedure_names:
                term_score = max(term_score, 5.0)
            if anchor_terms and len(term) >= 4 and term in anchor_terms:
                term_score = max(term_score, 3.0)
            if text and len(term) >= 4 and term in text:
                term_score = max(term_score, 1.0)
            if term_score > 0:
                matched.append(term)
                score += term_score
        return score, matched

    @staticmethod
    def _token_overlap_score(term: str, clause_title: str) -> float:
        if not term or not clause_title:
            return 0.0
        term_tokens = [token for token in normalize_anchor(term).split() if token]
        title_tokens = set(normalize_anchor(clause_title).split())
        if not term_tokens or not title_tokens:
            return 0.0
        overlap = len([token for token in term_tokens if token in title_tokens])
        if overlap < 2:
            return 0.0
        return 2.5 + (1.3 * overlap)


class MultiHopRetrievalPipeline:
    def __init__(self, backend: MultiHopBackend, registry: QueryFeatureRegistry | None = None) -> None:
        self.backend = backend
        self.registry = registry or QueryFeatureRegistry()

    def run(self, query_text: str, limit: int = 10) -> dict:
        normalized = normalize_query(query_text, registry=self.registry)
        direct_hits = self.backend.search(
            [
                *normalized.features.get("tokens", []),
                *normalized.aliases,
                *normalized.candidate_anchors,
                normalized.normalized_query,
            ],
            limit=max(limit * 2, 10),
            stage_filters=normalized.stage_filters or None,
        )
        scored_hits = []
        for hit in direct_hits:
            signals = collect_relevance_signals(normalized, hit.doc, retrieval_score=hit.score)
            relevance_score, breakdown = score_relevance(signals)
            if relevance_score <= 0:
                continue
            scored_hits.append(
                {
                    "doc": hit.doc,
                    "doc_id": hit.doc.doc_id,
                    "score": relevance_score,
                    "reason_type": hit.reason_type,
                    "matched_text": hit.matched_text,
                    "relevance_breakdown": breakdown,
                }
            )

        seed_docs = [item["doc"] for item in scored_hits[:limit]]
        anchor_candidates = extract_anchor_candidates(seed_docs)
        query_terms = [normalized.normalized_query, *normalized.candidate_anchors, *normalized.features.get("tokens", [])]
        filtered_anchor_candidates = []
        for item in anchor_candidates:
            overlap = _anchor_query_overlap(item["anchor"], query_terms)
            if overlap <= 0 and "clause_title" not in item.get("sources", []):
                continue
            filtered_anchor_candidates.append({**item, "query_overlap": overlap})
        selected_anchors = select_anchors(filtered_anchor_candidates, limit=8)
        hop_stage_filters = infer_hop_stage_targets(seed_docs)

        expansion_hits = []
        for anchor in selected_anchors:
            for hit in self.backend.search([anchor["anchor"]], limit=limit, stage_filters=hop_stage_filters):
                expansion_hits.append(
                    {
                        "doc": hit.doc,
                        "doc_id": hit.doc.doc_id,
                        "score": round(hit.score + anchor["score"], 3),
                        "reason_type": "anchor_hit",
                        "matched_text": anchor["anchor"],
                        "relevance_breakdown": {"anchor_selection": anchor["score"]},
                    }
                )

        merged_hits = merge_clause_results([*scored_hits, *expansion_hits])
        return {
            "query": normalized,
            "direct_hits": scored_hits[:limit],
            "selected_anchors": selected_anchors,
            "expanded_hits": expansion_hits[: limit * 2],
            "merged_clauses": merged_hits[:limit],
            "hop_stage_filters": hop_stage_filters,
        }
