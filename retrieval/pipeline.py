from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Protocol

from parser.models import DocRecord
from retrieval.query_normalizer import NormalizedQuery, QueryFeatureRegistry, normalize_query
from retrieval.signal_collector import collect_expansion_signals
from retrieval.spec_ranker import rank_specs


@dataclass
class SearchHit:
    doc: DocRecord
    score: float
    reason_type: str
    matched_text: str


class SearchBackend(Protocol):
    def search(self, terms: Iterable[str], limit: int = 20) -> list[SearchHit]:
        ...


class InMemoryBackend:
    def __init__(self, records: Iterable[DocRecord]) -> None:
        self.records = list(records)

    def search(self, terms: Iterable[str], limit: int = 20) -> list[SearchHit]:
        normalized_terms = []
        for term in terms:
            candidate = term.strip().lower()
            if not candidate or candidate in normalized_terms:
                continue
            normalized_terms.append(candidate)
        hits: list[SearchHit] = []
        for record in self.records:
            haystacks = [
                record.embedding_text or record.text,
                " ".join(record.anchor_terms),
                " ".join(record.keywords),
                record.row_header,
                record.table_title,
            ]
            content = "\n".join(part for part in haystacks if part).lower()
            score = 0.0
            matched: list[str] = []
            for term in normalized_terms:
                if term and term in content:
                    score += 1.0 + (0.3 if term in " ".join(record.anchor_terms).lower() else 0.0)
                    matched.append(term)
            if score:
                reason_type = "table_row_hit" if record.doc_type == "table_row_doc" else "direct_hit"
                hits.append(
                    SearchHit(
                        doc=record,
                        score=score,
                        reason_type=reason_type,
                        matched_text=", ".join(matched[:5]),
                    )
                )
        hits.sort(key=lambda item: (-item.score, item.doc.doc_id))
        return hits[:limit]


class RetrievalPipeline:
    def __init__(self, backend: SearchBackend, registry: QueryFeatureRegistry | None = None) -> None:
        self.backend = backend
        self.registry = registry or QueryFeatureRegistry()

    def direct_search(self, query: NormalizedQuery, limit: int = 10) -> list[SearchHit]:
        terms = [
            *query.aliases,
            *query.hinted_specs,
            *query.hinted_stages,
            *query.features.get("tokens", []),
            *query.candidate_anchors,
            query.normalized_query,
        ]
        return self.backend.search(terms, limit=limit)

    def collect_expansion_signals(self, seed_docs: Iterable[DocRecord]) -> list[dict]:
        return collect_expansion_signals(seed_docs)

    def expanded_search(self, signals: Iterable[dict], limit: int = 20) -> list[SearchHit]:
        terms = [signal["signal"] for signal in signals if signal.get("classification") in {"strong", "normal"}]
        return self.backend.search(terms, limit=limit)

    def merge_results(self, direct_hits: Iterable[SearchHit], expanded_hits: Iterable[SearchHit]) -> list[dict]:
        merged: dict[str, dict] = {}
        for hit in [*direct_hits, *expanded_hits]:
            existing = merged.get(hit.doc.doc_id)
            payload = {
                "doc_id": hit.doc.doc_id,
                "spec_no": hit.doc.spec_no,
                "score": hit.score,
                "reason_type": hit.reason_type,
                "matched_text": hit.matched_text,
                "explanation": f"{hit.reason_type} matched {hit.matched_text}",
                "doc": hit.doc,
            }
            if existing is None or existing["score"] < payload["score"]:
                merged[hit.doc.doc_id] = payload
        return sorted(merged.values(), key=lambda item: (-item["score"], item["doc_id"]))

    def rank_specs(self, merged_hits: Iterable[dict]) -> list[dict]:
        return rank_specs(merged_hits)

    def run(self, query_text: str, limit: int = 10) -> dict:
        normalized = normalize_query(query_text, registry=self.registry)
        direct_hits = self.direct_search(normalized, limit=limit)
        seed_docs = [hit.doc for hit in direct_hits]
        signals = self.collect_expansion_signals(seed_docs)
        expanded_hits = self.expanded_search(signals[:10], limit=limit)
        merged = self.merge_results(direct_hits, expanded_hits)
        ranked_specs = self.rank_specs(merged)
        return {
            "query": normalized,
            "direct_hits": direct_hits,
            "signals": signals,
            "expanded_hits": expanded_hits,
            "merged_hits": merged,
            "ranked_specs": ranked_specs,
        }
