from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from embedding.config import DEFAULT_EMBEDDING_DEVICE, DEFAULT_EMBEDDING_MODEL
from embedding.registry import create_embedding_provider
from retrieval.query_normalizer import QueryFeatureRegistry, normalize_query
from retrieval.vespa_adapter import build_vespa_query
from vespa.http_adapter import VespaEndpoint, query_vespa


def load_judgments(path: str | Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def reciprocal_rank_doc(hits: list[dict[str, Any]], relevant_doc_ids: set[str]) -> float:
    for index, hit in enumerate(hits, start=1):
        doc_id = hit.get("fields", {}).get("doc_id")
        if doc_id in relevant_doc_ids:
            return 1.0 / index
    return 0.0


def reciprocal_rank_spec(hits: list[dict[str, Any]], relevant_specs: set[str]) -> float:
    for index, hit in enumerate(hits, start=1):
        spec_no = hit.get("fields", {}).get("spec_no")
        if spec_no in relevant_specs:
            return 1.0 / index
    return 0.0


def recall_at_k_doc(hits: list[dict[str, Any]], relevant_doc_ids: set[str], k: int) -> float:
    returned = {hit.get("fields", {}).get("doc_id") for hit in hits[:k]}
    return 1.0 if returned.intersection(relevant_doc_ids) else 0.0


def recall_at_k_spec(hits: list[dict[str, Any]], relevant_specs: set[str], k: int) -> float:
    returned = {hit.get("fields", {}).get("spec_no") for hit in hits[:k]}
    return 1.0 if returned.intersection(relevant_specs) else 0.0


def ndcg_at_k_doc(hits: list[dict[str, Any]], relevant_doc_ids: set[str], k: int) -> float:
    dcg = 0.0
    for index, hit in enumerate(hits[:k], start=1):
        doc_id = hit.get("fields", {}).get("doc_id")
        if doc_id in relevant_doc_ids:
            dcg += 1.0 / (1.0 if index == 1 else math.log2(index + 1))
    ideal = 0.0
    for index in range(1, min(len(relevant_doc_ids), k) + 1):
        ideal += 1.0 / (1.0 if index == 1 else math.log2(index + 1))
    return dcg / ideal if ideal else 0.0


def build_query_response(
    endpoint: VespaEndpoint,
    query_text: str,
    profile: str,
    limit: int,
    registry: QueryFeatureRegistry,
    provider: Any | None,
    sparse_boost: float,
    vector_boost: float,
    timeout: float,
) -> dict[str, Any]:
    query_vector = provider.embed_texts([query_text], prompt_name="query")[0] if provider else None
    normalized = normalize_query(query_text, registry=registry, query_vector=query_vector)
    request = build_vespa_query(normalized, hits=limit)
    request.ranking = profile
    request.additional_params["presentation.summary"] = "short"
    request.additional_params["ranking.features.query(sparse_boost)"] = sparse_boost
    request.additional_params["ranking.features.query(vector_boost)"] = vector_boost
    return query_vespa(endpoint, request.to_params(), timeout=timeout)


def evaluate(
    judgments: list[dict[str, Any]],
    endpoint: VespaEndpoint,
    profile: str,
    limit: int,
    registry: QueryFeatureRegistry,
    provider: Any | None,
    sparse_boost: float,
    vector_boost: float,
    timeout: float,
) -> dict[str, Any]:
    totals = {
        "mrr_doc": 0.0,
        "mrr_spec": 0.0,
        "recall_doc_at_5": 0.0,
        "recall_doc_at_10": 0.0,
        "recall_spec_at_5": 0.0,
        "recall_spec_at_10": 0.0,
        "ndcg_doc_at_10": 0.0,
    }
    details: list[dict[str, Any]] = []

    for row in judgments:
        response = build_query_response(
            endpoint=endpoint,
            query_text=row["query"],
            profile=profile,
            limit=limit,
            registry=registry,
            provider=provider,
            sparse_boost=sparse_boost,
            vector_boost=vector_boost,
            timeout=timeout,
        )
        hits = response.get("root", {}).get("children", [])
        relevant_doc_ids = set(row.get("relevant_doc_ids", []))
        relevant_specs = set(row.get("relevant_specs", []))
        totals["mrr_doc"] += reciprocal_rank_doc(hits, relevant_doc_ids)
        totals["mrr_spec"] += reciprocal_rank_spec(hits, relevant_specs)
        totals["recall_doc_at_5"] += recall_at_k_doc(hits, relevant_doc_ids, 5)
        totals["recall_doc_at_10"] += recall_at_k_doc(hits, relevant_doc_ids, 10)
        totals["recall_spec_at_5"] += recall_at_k_spec(hits, relevant_specs, 5)
        totals["recall_spec_at_10"] += recall_at_k_spec(hits, relevant_specs, 10)
        totals["ndcg_doc_at_10"] += ndcg_at_k_doc(hits, relevant_doc_ids, 10)
        details.append(
            {
                "query": row["query"],
                "top_doc_ids": [hit.get("fields", {}).get("doc_id") for hit in hits[:5]],
                "top_specs": [hit.get("fields", {}).get("spec_no") for hit in hits[:5]],
                "top_relevance": [hit.get("relevance") for hit in hits[:5]],
            }
        )

    count = max(len(judgments), 1)
    return {
        "profile": profile,
        "sparse_boost": sparse_boost,
        "vector_boost": vector_boost,
        "judgment_count": len(judgments),
        "mrr_doc": totals["mrr_doc"] / count,
        "mrr_spec": totals["mrr_spec"] / count,
        "recall_doc_at_5": totals["recall_doc_at_5"] / count,
        "recall_doc_at_10": totals["recall_doc_at_10"] / count,
        "recall_spec_at_5": totals["recall_spec_at_5"] / count,
        "recall_spec_at_10": totals["recall_spec_at_10"] / count,
        "ndcg_doc_at_10": totals["ndcg_doc_at_10"] / count,
        "details": details,
    }


def parse_sweep(values: list[str]) -> list[tuple[str, float, float]]:
    parsed: list[tuple[str, float, float]] = []
    for value in values:
        parts = value.split(":")
        if len(parts) != 3:
            raise ValueError(f"Invalid sweep item: {value}. Expected profile:sparse_boost:vector_boost")
        profile, sparse_boost, vector_boost = parts
        parsed.append((profile, float(sparse_boost), float(vector_boost)))
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate Vespa ranking profiles with judgment JSONL")
    parser.add_argument("--judgments", required=True, help="Judgment JSONL path")
    parser.add_argument("--base-url", default="http://localhost:8080", help="Vespa base URL")
    parser.add_argument("--schema", default="spec_finder", help="Vespa schema name")
    parser.add_argument("--namespace", default="spec_finder", help="Vespa document namespace")
    parser.add_argument("--profile", default="hybrid", help="Single ranking profile to evaluate")
    parser.add_argument("--limit", type=int, default=10, help="Requested hit count")
    parser.add_argument("--registry", help="Optional query feature registry JSON")
    parser.add_argument("--embed-model", default=DEFAULT_EMBEDDING_MODEL, help="Embedding model for query vectors")
    parser.add_argument("--local-model-dir", help="Optional local Hugging Face model directory")
    parser.add_argument("--output-dim", type=int, help="Optional embedding output dimension")
    parser.add_argument("--device", default=DEFAULT_EMBEDDING_DEVICE, help="Embedding device")
    parser.add_argument("--max-length", type=int, default=4096, help="Max token length for supported models")
    parser.add_argument("--no-4bit", action="store_true", help="Disable 4-bit loading for supported models")
    parser.add_argument("--sparse-boost", type=float, default=1.0, help="Sparse score weight")
    parser.add_argument("--vector-boost", type=float, default=1.0, help="Dense score weight")
    parser.add_argument("--timeout", type=float, default=60.0, help="Query timeout in seconds")
    parser.add_argument(
        "--sweep",
        nargs="*",
        default=[],
        help="Optional sweep items in profile:sparse_boost:vector_boost form",
    )
    parser.add_argument("--output", help="Optional output path for JSON results")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    judgments = load_judgments(args.judgments)
    registry = QueryFeatureRegistry.from_json(args.registry)
    endpoint = VespaEndpoint(base_url=args.base_url, schema=args.schema, namespace=args.namespace)
    provider = None
    if args.embed_model:
        provider = create_embedding_provider(
            args.embed_model,
            local_dir=args.local_model_dir,
            output_dim=args.output_dim,
            device=args.device,
            load_in_4bit=not args.no_4bit,
            max_length=args.max_length,
        )

    sweeps = parse_sweep(args.sweep) if args.sweep else [(args.profile, args.sparse_boost, args.vector_boost)]
    results = [
        evaluate(
            judgments=judgments,
            endpoint=endpoint,
            profile=profile,
            limit=args.limit,
            registry=registry,
            provider=provider if profile == "hybrid" else None,
            sparse_boost=sparse_boost,
            vector_boost=vector_boost,
            timeout=args.timeout,
        )
        for profile, sparse_boost, vector_boost in sweeps
    ]

    payload: dict[str, Any] = {"results": results}
    output = json.dumps(payload, ensure_ascii=True, indent=2)
    if args.output:
        Path(args.output).write_text(output + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
