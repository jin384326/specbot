from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Iterable

from embedding.providers import EmbeddingProvider
from parser.models import BaseDocRecord, DocRecord, doc_record_from_dict
from retrieval.multi_hop_pipeline import MultiHopSearchHit
from retrieval.query_normalizer import QueryFeatureRegistry, normalize_query
from retrieval.vespa_adapter import build_vespa_query
from vespa.http_adapter import VespaEndpoint, query_vespa


def _normalize_stage_filter_for_query(value: str) -> str:
    lowered = value.strip().lower()
    if lowered in {"stage 2", "stage2"}:
        return "stage2"
    if lowered in {"stage 3", "stage3"}:
        return "stage3"
    return "else"


def _content_kind_for_doc_type(doc_type: str) -> str:
    return {
        "clause_doc": "clause",
        "passage_doc": "passage",
        "table_doc": "table",
        "table_row_doc": "table_row",
        "entity_doc": "entity",
    }.get(doc_type, "clause")


def doc_record_from_vespa_hit(hit: dict[str, Any]) -> DocRecord:
    fields = dict(hit.get("fields", {}))
    fields.setdefault("content_kind", _content_kind_for_doc_type(fields.get("doc_type", "clause_doc")))
    if "summary_text" in fields and "summary" not in fields:
        fields["summary"] = fields.pop("summary_text")
    if "table_raw_json" in fields and "table_raw" not in fields:
        try:
            fields["table_raw"] = json.loads(fields.pop("table_raw_json"))
        except json.JSONDecodeError:
            fields["table_raw"] = []
    list_fields = [
        "clause_path",
        "keywords",
        "anchor_terms",
        "ie_names",
        "message_names",
        "procedure_names",
        "table_headers",
        "acronyms",
        "camel_case_identifiers",
        "referenced_specs",
        "referenced_clauses",
        "domain_hint",
        "row_cells",
        "table_raw",
        "dense_vector",
    ]
    for field_name in list_fields:
        fields.setdefault(field_name, [])
    fields.setdefault("entity_type", "")
    fields.setdefault("entity_name", "")
    fields.setdefault("source_doc_id", "")
    allowed_keys = set(BaseDocRecord.__dataclass_fields__.keys())
    sanitized = {key: value for key, value in fields.items() if key in allowed_keys}
    return doc_record_from_dict(sanitized)


@dataclass
class VespaMultiHopBackend:
    endpoint: VespaEndpoint
    registry: QueryFeatureRegistry | None = None
    embedding_provider: EmbeddingProvider | None = None
    ranking: str = "hybrid"
    summary: str = "short"
    sparse_boost: float = 0.0
    vector_boost: float = 1.0
    anchor_boost: float = 1.15
    title_boost: float = 1.2
    stage_boost: float = 1.1
    timeout: float = 30.0
    max_retries: int = 1
    retry_backoff_seconds: float = 0.5
    max_hits_per_call: int = 10
    records: list[DocRecord] = field(default_factory=list)
    _query_vector_cache: dict[str, list[float]] = field(default_factory=dict)

    def search(
        self,
        terms: Iterable[str],
        limit: int = 20,
        stage_filters: list[str] | None = None,
        spec_filters: list[str] | None = None,
    ) -> list[MultiHopSearchHit]:
        query_text = next((term.strip() for term in terms if term and term.strip()), "")
        if not query_text:
            return []
        normalized_stage_filters = stage_filters or [None]
        aggregated_hits: dict[str, MultiHopSearchHit] = {}
        for stage_filter in normalized_stage_filters:
            normalized = normalize_query(
                query_text,
                registry=self.registry,
                query_vector=self._get_query_vector(query_text),
                stage_filters=[_normalize_stage_filter_for_query(stage_filter)] if stage_filter else None,
            )
            if spec_filters:
                normalized.hinted_specs = list(spec_filters)
                normalized.inferred_specs = []
                normalized.features["hinted_specs"] = list(spec_filters)
                normalized.features["inferred_specs"] = []
            request = build_vespa_query(normalized, hits=min(limit, self.max_hits_per_call))
            request.ranking = self.ranking
            request.additional_params["presentation.summary"] = self.summary
            request.additional_params["ranking.features.query(anchor_boost)"] = self.anchor_boost
            request.additional_params["ranking.features.query(title_boost)"] = self.title_boost
            request.additional_params["ranking.features.query(stage_boost)"] = self.stage_boost
            request.additional_params["ranking.features.query(sparse_boost)"] = self.sparse_boost
            request.additional_params["ranking.features.query(vector_boost)"] = self.vector_boost
            response = query_vespa(
                self.endpoint,
                request.to_params(),
                timeout=self.timeout,
                max_retries=self.max_retries,
                retry_backoff_seconds=self.retry_backoff_seconds,
            )

            for child in response.get("root", {}).get("children", []):
                record = doc_record_from_vespa_hit(child)
                hit = MultiHopSearchHit(
                    doc=record,
                    score=float(child.get("relevance", 0.0)),
                    reason_type="vespa_hit",
                    matched_text=query_text,
                    metadata={"stage_filter": stage_filter or "", "raw_hit": child},
                )
                existing = aggregated_hits.get(record.doc_id)
                if existing is None or hit.score > existing.score:
                    aggregated_hits[record.doc_id] = hit
        return sorted(aggregated_hits.values(), key=lambda item: (-item.score, item.doc.doc_id))[:limit]

    def _get_query_vector(self, query_text: str) -> list[float]:
        if self.embedding_provider is None:
            return []
        cached = self._query_vector_cache.get(query_text)
        if cached is not None:
            return cached
        vector = self.embedding_provider.embed_texts([query_text], prompt_name="query")[0]
        self._query_vector_cache[query_text] = vector
        return vector
