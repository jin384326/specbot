from __future__ import annotations

import argparse
import json
from pathlib import Path

from embedding.config import DEFAULT_EMBEDDING_DEVICE, DEFAULT_EMBEDDING_MODEL
from embedding.build_embeddings import build_embeddings
from embedding.registry import create_embedding_provider
from huggingface_hub import snapshot_download
from enrich.build_anchor_candidates import build_anchor_candidates
from enrich.enrich_metadata import enrich_corpus, load_jsonl
from parser.corpus_builder import build_corpus
from retrieval.pipeline import InMemoryBackend, RetrievalPipeline
from retrieval.centered_multi_hop_pipeline import CenteredMultiHopRetrievalPipeline
from retrieval.llm_selector import HeuristicSelectionLLM, OpenAISelectionLLM
from retrieval.vespa_multi_hop_backend import VespaMultiHopBackend
from retrieval.query_normalizer import QueryFeatureRegistry, build_query_feature_registry_from_corpus, normalize_query
from retrieval.vespa_adapter import build_vespa_query
from download.ftp_download import download_file_ftp, download_dir_ftp
from download.zip_extract import extract_docx_from_zip
from vespa.export_for_vespa import export_corpus_to_vespa_feed
from vespa.http_adapter import (
    VespaEndpoint,
    build_application_package_bytes,
    deploy_application_package,
    feed_jsonl_file,
    query_vespa,
    smoke_test_vespa,
    wait_for_vespa,
)


def load_metadata_map(path: str | None) -> dict[str, dict]:
    if path is None:
        return {}
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def cmd_build_corpus(args: argparse.Namespace) -> None:
    metadata = load_metadata_map(args.metadata)
    count = build_corpus(
        args.inputs,
        args.output,
        metadata_by_source=metadata,
        append=not args.overwrite,
    )
    print(f"Wrote {count} corpus records to {args.output}")


def cmd_enrich_corpus(args: argparse.Namespace) -> None:
    count = enrich_corpus(args.input, args.output, taxonomy_path=args.taxonomy)
    print(f"Wrote {count} enriched corpus records to {args.output}")


def cmd_build_anchors(args: argparse.Namespace) -> None:
    build_anchor_candidates(args.input, args.output)
    print(f"Wrote anchor candidates to {args.output}")


def cmd_build_query_registry(args: argparse.Namespace) -> None:
    registry = build_query_feature_registry_from_corpus(args.input)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(registry.to_dict(), ensure_ascii=True, indent=2), encoding="utf-8")
    print(f"Wrote query registry to {args.output}")


def cmd_build_embeddings(args: argparse.Namespace) -> None:
    count = build_embeddings(
        args.input,
        args.output,
        model_name=args.model,
        local_dir=args.local_model_dir,
        output_dim=args.output_dim,
        device=args.device,
        load_in_4bit=not args.no_4bit,
        batch_size=args.batch_size,
        offset=args.offset,
        limit=args.limit,
        max_length=args.max_length,
        append=args.append,
    )
    print(f"Wrote embeddings for {count} records to {args.output}")


def cmd_download_hf_model(args: argparse.Namespace) -> None:
    path = snapshot_download(
        repo_id=args.repo_id,
        local_dir=args.local_dir,
        local_dir_use_symlinks=False,
        resume_download=True,
    )
    print(f"Downloaded model to {path}")


def cmd_download_specs_ftp(args: argparse.Namespace) -> None:
    import os

    password = args.password or os.environ.get("FTP_PASSWORD", "")
    if args.file:
        download_file_ftp(
            args.host,
            args.file,
            Path(args.local_dir) / Path(args.file).name,
            port=args.port,
            user=args.user,
            password=password or None,
            timeout=args.timeout,
        )
        print(f"Downloaded {args.file} to {args.local_dir}")
    else:
        paths = download_dir_ftp(
            args.host,
            args.remote_dir or "",
            args.local_dir,
            pattern=args.pattern,
            port=args.port,
            user=args.user,
            password=password or None,
            timeout=args.timeout,
            recurse=not getattr(args, "no_recurse", False),
        )
        print(f"Downloaded {len(paths)} file(s) to {args.local_dir}")


def cmd_extract_docx_from_zip(args: argparse.Namespace) -> None:
    paths = extract_docx_from_zip(
        args.input,
        args.output,
        flatten=args.flatten,
    )
    print(f"Extracted {len(paths)} .docx file(s) to {args.output}")


def cmd_demo_query(args: argparse.Namespace) -> None:
    records = load_jsonl(args.input)
    registry = QueryFeatureRegistry.from_json(args.registry)
    backend = InMemoryBackend(records)
    pipeline = RetrievalPipeline(backend, registry=registry)
    result = pipeline.run(args.query, limit=args.limit)
    payload = {
        "query": result["query"].to_dict(),
        "ranked_specs": result["ranked_specs"][: args.limit],
        "signals": result["signals"][: args.limit],
        "top_hits": [
            {
                "doc_id": hit["doc_id"],
                "spec_no": hit["spec_no"],
                "score": hit["score"],
                "reason_type": hit["reason_type"],
                "matched_text": hit["matched_text"],
            }
            for hit in result["merged_hits"][: args.limit]
        ],
    }
    print(json.dumps(payload, ensure_ascii=True, indent=2))


def cmd_export_vespa(args: argparse.Namespace) -> None:
    count = export_corpus_to_vespa_feed(args.input, args.output)
    print(f"Wrote {count} Vespa feed documents to {args.output}")


def cmd_preview_vespa_query(args: argparse.Namespace) -> None:
    registry = QueryFeatureRegistry.from_json(args.registry)
    query_vector = None
    if args.embed_model:
        query_vector = create_embedding_provider(
            args.embed_model,
            local_dir=args.local_model_dir,
            output_dim=args.output_dim,
            device=args.device,
            load_in_4bit=not args.no_4bit,
            max_length=args.max_length,
        ).embed_texts([args.query], prompt_name="query")[0]
    normalized = normalize_query(args.query, registry=registry, query_vector=query_vector, stage_filters=args.stage_filter)
    request = build_vespa_query(normalized, hits=args.limit)
    if args.ranking:
        request.ranking = args.ranking
    print(json.dumps(request.to_params(), ensure_ascii=True, indent=2))


def cmd_feed_vespa_http(args: argparse.Namespace) -> None:
    endpoint = VespaEndpoint(
        base_url=args.base_url,
        schema=args.schema,
        namespace=args.namespace,
        config_base_url=args.config_base_url,
    )
    results = feed_jsonl_file(
        endpoint,
        args.input,
        timeout=args.timeout,
        max_retries=args.max_retries,
        retry_backoff_seconds=args.retry_backoff_seconds,
        batch_size=args.batch_size,
        max_workers=args.max_workers,
    )
    if args.failed_only:
        results["attempts"] = [item for item in results["attempts"] if not item["success"]]
    print(json.dumps({"base_url": args.base_url, **results}, ensure_ascii=True, indent=2))


def cmd_query_vespa_http(args: argparse.Namespace) -> None:
    registry = QueryFeatureRegistry.from_json(args.registry)
    query_vector = None
    if args.embed_model:
        query_vector = create_embedding_provider(
            args.embed_model,
            local_dir=args.local_model_dir,
            output_dim=args.output_dim,
            device=args.device,
            load_in_4bit=not args.no_4bit,
            max_length=args.max_length,
        ).embed_texts([args.query], prompt_name="query")[0]
    normalized = normalize_query(args.query, registry=registry, query_vector=query_vector, stage_filters=args.stage_filter)
    request = build_vespa_query(normalized, hits=args.limit)
    request.ranking = args.ranking
    request.additional_params["presentation.summary"] = args.summary
    request.additional_params["ranking.features.query(anchor_boost)"] = args.anchor_boost
    request.additional_params["ranking.features.query(title_boost)"] = args.title_boost
    request.additional_params["ranking.features.query(stage_boost)"] = args.stage_boost
    request.additional_params["ranking.features.query(sparse_boost)"] = args.sparse_boost
    request.additional_params["ranking.features.query(vector_boost)"] = args.vector_boost
    endpoint = VespaEndpoint(
        base_url=args.base_url,
        schema=args.schema,
        namespace=args.namespace,
        config_base_url=args.config_base_url,
    )
    response = query_vespa(
        endpoint,
        request.to_params(),
        timeout=args.timeout,
        max_retries=args.max_retries,
        retry_backoff_seconds=args.retry_backoff_seconds,
    )
    print(json.dumps(response, ensure_ascii=True, indent=2))


def cmd_centered_query_vespa_http(args: argparse.Namespace) -> None:
    registry = QueryFeatureRegistry.from_json(args.registry)
    embedding_provider = None
    if args.embed_model:
        embedding_provider = create_embedding_provider(
            args.embed_model,
            local_dir=args.local_model_dir,
            output_dim=args.output_dim,
            device=args.device,
            load_in_4bit=not args.no_4bit,
            max_length=args.max_length,
        )
    routing_records = load_jsonl(args.routing_corpus) if args.routing_corpus else []
    endpoint = VespaEndpoint(
        base_url=args.base_url,
        schema=args.schema,
        namespace=args.namespace,
        config_base_url=args.config_base_url,
    )
    selector = HeuristicSelectionLLM()
    if args.use_llm_selector:
        selector = OpenAISelectionLLM.from_env(model=args.openai_model) or selector
    backend = VespaMultiHopBackend(
        endpoint=endpoint,
        registry=registry,
        embedding_provider=embedding_provider,
        ranking=args.ranking,
        summary=args.summary,
        sparse_boost=args.sparse_boost,
        vector_boost=args.vector_boost,
        anchor_boost=args.anchor_boost,
        title_boost=args.title_boost,
        stage_boost=args.stage_boost,
        timeout=args.timeout,
        max_retries=args.max_retries,
        retry_backoff_seconds=args.retry_backoff_seconds,
        records=routing_records,
    )
    pipeline = CenteredMultiHopRetrievalPipeline(backend=backend, registry=registry, selector=selector)
    if args.llm_relevance_only:
        pipeline.llm_relevance_only = True
    result = pipeline.run(args.query, limit=args.limit)
    payload = {
        "query": result["query"].to_dict(),
        "entry_specs": result["entry_specs"],
        "stage_buckets": result["stage_buckets"],
        "selected_anchors": result["selected_anchors"][: args.limit],
        "merged_clauses": [
            {
                "spec_no": item["spec_no"],
                "clause_id": item["clause_id"],
                "clause_title": item["clause_title"],
                "score": item["score"],
                "ranking_adjustment": item.get("ranking_adjustment", {}),
            }
            for item in result["merged_clauses"][: args.limit]
        ],
    }
    print(json.dumps(payload, ensure_ascii=True, indent=2))


def cmd_package_vespa_app(args: argparse.Namespace) -> None:
    payload = build_application_package_bytes(args.app_dir)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(payload)
    print(f"Wrote Vespa application package to {args.output}")


def cmd_deploy_vespa_http(args: argparse.Namespace) -> None:
    endpoint = VespaEndpoint(
        base_url=args.base_url,
        schema=args.schema,
        namespace=args.namespace,
        config_base_url=args.config_base_url,
    )
    result = deploy_application_package(
        endpoint,
        args.app_dir,
        timeout=args.timeout,
        max_retries=args.max_retries,
        retry_backoff_seconds=args.retry_backoff_seconds,
    )
    print(json.dumps(result, ensure_ascii=True, indent=2))


def cmd_smoke_test_vespa_http(args: argparse.Namespace) -> None:
    registry = QueryFeatureRegistry.from_json(args.registry)
    query_vector = None
    if args.embed_model:
        query_vector = create_embedding_provider(
            args.embed_model,
            local_dir=args.local_model_dir,
            output_dim=args.output_dim,
            device=args.device,
            load_in_4bit=not args.no_4bit,
            max_length=args.max_length,
        ).embed_texts([args.query], prompt_name="query")[0]
    normalized = normalize_query(args.query, registry=registry, query_vector=query_vector, stage_filters=args.stage_filter)
    request = build_vespa_query(normalized, hits=args.limit)
    request.ranking = args.ranking
    request.additional_params["presentation.summary"] = args.summary
    request.additional_params["ranking.features.query(sparse_boost)"] = args.sparse_boost
    request.additional_params["ranking.features.query(vector_boost)"] = args.vector_boost
    endpoint = VespaEndpoint(
        base_url=args.base_url,
        schema=args.schema,
        namespace=args.namespace,
        config_base_url=args.config_base_url,
    )
    result = smoke_test_vespa(endpoint, request.to_params(), timeout=args.timeout)
    print(json.dumps(result, ensure_ascii=True, indent=2))


def cmd_wait_for_vespa_http(args: argparse.Namespace) -> None:
    endpoint = VespaEndpoint(
        base_url=args.base_url,
        schema=args.schema,
        namespace=args.namespace,
        config_base_url=args.config_base_url,
    )
    result = wait_for_vespa(
        endpoint,
        timeout_seconds=args.timeout,
        poll_interval_seconds=args.poll_interval,
        require_config=args.require_config,
    )
    print(json.dumps(result, ensure_ascii=True, indent=2))
    if not result["ready"]:
        raise SystemExit(1)


def cmd_vespa_e2e_http(args: argparse.Namespace) -> None:
    registry = QueryFeatureRegistry.from_json(args.registry)
    endpoint = VespaEndpoint(
        base_url=args.base_url,
        schema=args.schema,
        namespace=args.namespace,
        config_base_url=args.config_base_url,
    )
    summary: dict[str, object] = {"base_url": args.base_url}

    if args.deploy:
        summary["deploy"] = deploy_application_package(
            endpoint,
            args.app_dir,
            timeout=args.deploy_timeout,
            max_retries=args.max_retries,
            retry_backoff_seconds=args.retry_backoff_seconds,
        )

    if args.wait:
        readiness = wait_for_vespa(
            endpoint,
            timeout_seconds=args.ready_timeout,
            poll_interval_seconds=args.poll_interval,
            require_config=args.require_config,
        )
        summary["readiness"] = readiness
        if not readiness["ready"]:
            print(json.dumps(summary, ensure_ascii=True, indent=2))
            raise SystemExit(1)

    if args.feed_input:
        summary["feed"] = feed_jsonl_file(
            endpoint,
            args.feed_input,
            timeout=args.feed_timeout,
            max_retries=args.max_retries,
            retry_backoff_seconds=args.retry_backoff_seconds,
            batch_size=args.batch_size,
        )

    if args.query:
        query_vector = None
        if args.embed_model:
            query_vector = create_embedding_provider(
                args.embed_model,
                local_dir=args.local_model_dir,
                output_dim=args.output_dim,
                device=args.device,
                load_in_4bit=not args.no_4bit,
                max_length=args.max_length,
            ).embed_texts([args.query], prompt_name="query")[0]
        normalized = normalize_query(args.query, registry=registry, query_vector=query_vector, stage_filters=args.stage_filter)
        request = build_vespa_query(normalized, hits=args.limit)
        request.ranking = args.ranking
        request.additional_params["presentation.summary"] = args.summary
        request.additional_params["ranking.features.query(anchor_boost)"] = args.anchor_boost
        request.additional_params["ranking.features.query(title_boost)"] = args.title_boost
        request.additional_params["ranking.features.query(stage_boost)"] = args.stage_boost
        request.additional_params["ranking.features.query(sparse_boost)"] = args.sparse_boost
        request.additional_params["ranking.features.query(vector_boost)"] = args.vector_boost
        summary["smoke_test"] = smoke_test_vespa(endpoint, request.to_params(), timeout=args.query_timeout)

    print(json.dumps(summary, ensure_ascii=True, indent=2))


def cmd_build_full_corpus_pipeline(args: argparse.Namespace) -> None:
    corpus_output = args.corpus_output
    enriched_output = args.enriched_output
    embedded_output = args.embedded_output
    vespa_output = args.vespa_output

    summary: dict[str, object] = {
        "inputs": args.inputs,
        "corpus_output": corpus_output,
        "enriched_output": enriched_output,
        "embedded_output": embedded_output,
        "vespa_output": vespa_output,
    }

    metadata = load_metadata_map(args.metadata)
    summary["build_corpus"] = {
        "count": build_corpus(
            args.inputs,
            corpus_output,
            metadata_by_source=metadata,
            append=False,
        )
    }
    summary["enrich_corpus"] = {"count": enrich_corpus(corpus_output, enriched_output, taxonomy_path=args.taxonomy)}
    summary["build_embeddings"] = {
        "count": build_embeddings(
            enriched_output,
            embedded_output,
            model_name=args.model,
            local_dir=args.local_model_dir,
            output_dim=args.output_dim,
            device=args.device,
            load_in_4bit=not args.no_4bit,
            batch_size=args.batch_size,
            offset=args.offset,
            limit=args.limit,
            max_length=args.max_length,
            append=False,
        )
    }
    summary["export_vespa"] = {"count": export_corpus_to_vespa_feed(embedded_output, vespa_output)}
    print(json.dumps(summary, ensure_ascii=True, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="3GPP Spec Finder CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build_cmd = subparsers.add_parser("build-corpus", help="Parse DOCX files into corpus.jsonl")
    build_cmd.add_argument("inputs", nargs="+", help="Input DOCX files, directories, or glob patterns")
    build_cmd.add_argument("--output", required=True, help="Output JSONL path")
    build_cmd.add_argument("--metadata", help="JSON metadata map keyed by file path or file name")
    build_cmd.add_argument("--overwrite", action="store_true", help="Overwrite output instead of appending")
    build_cmd.set_defaults(func=cmd_build_corpus)

    enrich_cmd = subparsers.add_parser("enrich-corpus", help="Enrich corpus metadata")
    enrich_cmd.add_argument("--input", required=True, help="Input corpus JSONL")
    enrich_cmd.add_argument("--output", required=True, help="Output enriched JSONL")
    enrich_cmd.add_argument("--taxonomy", help="Optional taxonomy JSON")
    enrich_cmd.set_defaults(func=cmd_enrich_corpus)

    anchors_cmd = subparsers.add_parser("build-anchors", help="Build anchor candidate scores")
    anchors_cmd.add_argument("--input", required=True, help="Input enriched corpus JSONL")
    anchors_cmd.add_argument("--output", required=True, help="Output anchor candidate JSONL")
    anchors_cmd.set_defaults(func=cmd_build_anchors)

    registry_cmd = subparsers.add_parser("build-query-registry", help="Build query-time spec hint registry from corpus")
    registry_cmd.add_argument("--input", required=True, help="Input enriched corpus JSONL")
    registry_cmd.add_argument("--output", required=True, help="Output registry JSON path")
    registry_cmd.set_defaults(func=cmd_build_query_registry)

    embeddings_cmd = subparsers.add_parser("build-embeddings", help="Build dense vectors for an enriched corpus")
    embeddings_cmd.add_argument("--input", required=True, help="Input enriched corpus JSONL")
    embeddings_cmd.add_argument("--output", required=True, help="Output JSONL with dense vectors")
    embeddings_cmd.add_argument("--model", default=DEFAULT_EMBEDDING_MODEL, help="Embedding model, e.g. hash-16, qwen3-embedding-0.6b, or sentence-transformers:all-MiniLM-L6-v2")
    embeddings_cmd.add_argument("--local-model-dir", help="Optional local Hugging Face model directory")
    embeddings_cmd.add_argument("--output-dim", type=int, help="Optional output dimension")
    embeddings_cmd.add_argument("--device", default=DEFAULT_EMBEDDING_DEVICE, help="Embedding device, e.g. cuda or cpu")
    embeddings_cmd.add_argument("--batch-size", type=int, default=4, help="Embedding batch size")
    embeddings_cmd.add_argument("--offset", type=int, default=0, help="Start offset in the input JSONL")
    embeddings_cmd.add_argument("--limit", type=int, help="Optional maximum number of records to embed")
    embeddings_cmd.add_argument("--max-length", type=int, default=2048, help="Max token length for supported models")
    embeddings_cmd.add_argument("--no-4bit", action="store_true", help="Disable 4-bit loading for supported models")
    embeddings_cmd.add_argument("--append", action="store_true", help="Append to output instead of overwriting it")
    embeddings_cmd.set_defaults(func=cmd_build_embeddings)

    download_cmd = subparsers.add_parser("download-hf-model", help="Download a Hugging Face model to a local directory")
    download_cmd.add_argument("--repo-id", required=True, help="Hugging Face repo id, e.g. Qwen/Qwen3-Embedding-0.6B")
    download_cmd.add_argument("--local-dir", required=True, help="Local directory to store the model")
    download_cmd.set_defaults(func=cmd_download_hf_model)

    ftp_cmd = subparsers.add_parser("download-specs-ftp", help="Download spec files (e.g. zip) from FTP server")
    ftp_cmd.add_argument("--host", required=True, help="FTP host")
    ftp_cmd.add_argument("--local-dir", required=True, help="Local directory to save files")
    ftp_cmd.add_argument("--file", help="Single remote file path to download (e.g. specs/23501.zip)")
    ftp_cmd.add_argument("--remote-dir", help="Remote directory to list and download from (used when --file is not set)")
    ftp_cmd.add_argument("--pattern", default="*.zip", help="Glob pattern for files when using --remote-dir (default: *.zip)")
    ftp_cmd.add_argument("--user", help="FTP user (optional)")
    ftp_cmd.add_argument("--password", help="FTP password (or set FTP_PASSWORD env)")
    ftp_cmd.add_argument("--port", type=int, default=21, help="FTP port (default: 21)")
    ftp_cmd.add_argument("--timeout", type=float, default=60.0, help="Connection timeout in seconds")
    ftp_cmd.add_argument("--no-recurse", action="store_true", help="Do not recurse into subdirectories when using --remote-dir")
    ftp_cmd.set_defaults(func=cmd_download_specs_ftp)

    extract_cmd = subparsers.add_parser("extract-docx-from-zip", help="Extract .docx files from a zip archive")
    extract_cmd.add_argument("--input", required=True, help="Input zip file path")
    extract_cmd.add_argument("--output", required=True, help="Output directory for extracted docx files")
    extract_cmd.add_argument("--flatten", action="store_true", help="Extract all docx into output dir with basename only (no subdirs)")
    extract_cmd.set_defaults(func=cmd_extract_docx_from_zip)

    demo_cmd = subparsers.add_parser("demo-query", help="Run an in-memory retrieval demo")
    demo_cmd.add_argument("--input", required=True, help="Input enriched corpus JSONL")
    demo_cmd.add_argument("--query", required=True, help="Natural language query")
    demo_cmd.add_argument("--limit", type=int, default=5, help="Max items to return")
    demo_cmd.add_argument("--registry", help="Optional query feature registry JSON")
    demo_cmd.set_defaults(func=cmd_demo_query)

    export_cmd = subparsers.add_parser("export-vespa", help="Export enriched corpus as Vespa feed JSONL")
    export_cmd.add_argument("--input", required=True, help="Input enriched corpus JSONL")
    export_cmd.add_argument("--output", required=True, help="Output Vespa feed JSONL")
    export_cmd.set_defaults(func=cmd_export_vespa)

    preview_cmd = subparsers.add_parser("preview-vespa-query", help="Build a Vespa query request preview")
    preview_cmd.add_argument("--query", required=True, help="Natural language query")
    preview_cmd.add_argument("--limit", type=int, default=10, help="Requested hit count")
    preview_cmd.add_argument("--registry", help="Optional query feature registry JSON")
    preview_cmd.add_argument("--embed-model", help="Optional embedding model for hybrid query preview")
    preview_cmd.add_argument("--ranking", help="Optional ranking profile override")
    preview_cmd.add_argument("--local-model-dir", help="Optional local Hugging Face model directory")
    preview_cmd.add_argument("--output-dim", type=int, help="Optional embedding output dimension")
    preview_cmd.add_argument("--device", default=DEFAULT_EMBEDDING_DEVICE, help="Embedding device for query vector creation")
    preview_cmd.add_argument("--max-length", type=int, default=2048, help="Max token length for supported models")
    preview_cmd.add_argument("--no-4bit", action="store_true", help="Disable 4-bit loading for supported models")
    preview_cmd.add_argument("--stage-filter", action="append", choices=["stage2", "stage3", "else"], help="Restrict search to a stage bucket")
    preview_cmd.set_defaults(func=cmd_preview_vespa_query)

    package_cmd = subparsers.add_parser("package-vespa-app", help="Zip the Vespa application package")
    package_cmd.add_argument("--app-dir", default="vespa/schema", help="Application package directory")
    package_cmd.add_argument("--output", required=True, help="Output zip path")
    package_cmd.set_defaults(func=cmd_package_vespa_app)

    deploy_cmd = subparsers.add_parser("deploy-vespa-http", help="Deploy the Vespa application package to config server")
    deploy_cmd.add_argument("--app-dir", default="vespa/schema", help="Application package directory")
    deploy_cmd.add_argument("--base-url", required=True, help="Vespa query/document base URL, e.g. http://localhost:8080")
    deploy_cmd.add_argument("--config-base-url", help="Vespa config server URL, e.g. http://localhost:19071")
    deploy_cmd.add_argument("--schema", default="spec_finder", help="Vespa schema name")
    deploy_cmd.add_argument("--namespace", default="spec_finder", help="Vespa document namespace")
    deploy_cmd.add_argument("--timeout", type=float, default=60.0, help="HTTP timeout in seconds")
    deploy_cmd.add_argument("--max-retries", type=int, default=1, help="Retries for transient deploy errors")
    deploy_cmd.add_argument("--retry-backoff-seconds", type=float, default=1.0, help="Linear backoff base in seconds")
    deploy_cmd.set_defaults(func=cmd_deploy_vespa_http)

    feed_http_cmd = subparsers.add_parser("feed-vespa-http", help="POST Vespa feed JSONL to a running Vespa endpoint")
    feed_http_cmd.add_argument("--input", required=True, help="Input Vespa feed JSONL")
    feed_http_cmd.add_argument("--base-url", required=True, help="Vespa base URL, e.g. http://localhost:8080")
    feed_http_cmd.add_argument("--config-base-url", help="Optional Vespa config server URL")
    feed_http_cmd.add_argument("--schema", default="spec_finder", help="Vespa schema name")
    feed_http_cmd.add_argument("--namespace", default="spec_finder", help="Vespa document namespace")
    feed_http_cmd.add_argument("--timeout", type=float, default=30.0, help="HTTP timeout in seconds")
    feed_http_cmd.add_argument("--batch-size", type=int, default=100, help="Feed request batch size")
    feed_http_cmd.add_argument("--max-workers", type=int, default=1, help="Concurrent HTTP feed workers")
    feed_http_cmd.add_argument("--max-retries", type=int, default=2, help="Retries per document for transient errors")
    feed_http_cmd.add_argument("--retry-backoff-seconds", type=float, default=0.5, help="Linear backoff base in seconds")
    feed_http_cmd.add_argument("--failed-only", action="store_true", help="Print only failed attempts")
    feed_http_cmd.set_defaults(func=cmd_feed_vespa_http)

    query_http_cmd = subparsers.add_parser("query-vespa-http", help="Query a running Vespa endpoint")
    query_http_cmd.add_argument("--query", required=True, help="Natural language query")
    query_http_cmd.add_argument("--base-url", required=True, help="Vespa base URL, e.g. http://localhost:8080")
    query_http_cmd.add_argument("--config-base-url", help="Optional Vespa config server URL")
    query_http_cmd.add_argument("--limit", type=int, default=10, help="Requested hit count")
    query_http_cmd.add_argument("--schema", default="spec_finder", help="Vespa schema name")
    query_http_cmd.add_argument("--namespace", default="spec_finder", help="Vespa document namespace")
    query_http_cmd.add_argument("--registry", help="Optional query feature registry JSON")
    query_http_cmd.add_argument("--timeout", type=float, default=30.0, help="HTTP timeout in seconds")
    query_http_cmd.add_argument("--ranking", default="hybrid", help="Vespa ranking profile")
    query_http_cmd.add_argument("--summary", default="short", help="Vespa summary class")
    query_http_cmd.add_argument("--anchor-boost", type=float, default=1.15, help="Query-time anchor boost")
    query_http_cmd.add_argument("--title-boost", type=float, default=1.2, help="Query-time title boost")
    query_http_cmd.add_argument("--stage-boost", type=float, default=1.1, help="Query-time stage boost")
    query_http_cmd.add_argument("--sparse-boost", type=float, default=1.25, help="Query-time sparse score boost")
    query_http_cmd.add_argument("--vector-boost", type=float, default=0.45, help="Query-time vector boost")
    query_http_cmd.add_argument("--embed-model", default=DEFAULT_EMBEDDING_MODEL, help="Optional embedding model for hybrid retrieval")
    query_http_cmd.add_argument("--local-model-dir", help="Optional local Hugging Face model directory")
    query_http_cmd.add_argument("--output-dim", type=int, help="Optional embedding output dimension")
    query_http_cmd.add_argument("--device", default=DEFAULT_EMBEDDING_DEVICE, help="Embedding device for query vector creation")
    query_http_cmd.add_argument("--max-length", type=int, default=2048, help="Max token length for supported models")
    query_http_cmd.add_argument("--no-4bit", action="store_true", help="Disable 4-bit loading for supported models")
    query_http_cmd.add_argument("--stage-filter", action="append", choices=["stage2", "stage3", "else"], help="Restrict search to a stage bucket")
    query_http_cmd.add_argument("--max-retries", type=int, default=1, help="Retries for transient query errors")
    query_http_cmd.add_argument("--retry-backoff-seconds", type=float, default=0.5, help="Linear backoff base in seconds")
    query_http_cmd.set_defaults(func=cmd_query_vespa_http)

    centered_query_cmd = subparsers.add_parser("centered-query-vespa-http", help="Run the centered multi-hop retrieval flow over live Vespa stage fan-out queries")
    centered_query_cmd.add_argument("--query", required=True, help="Natural language query")
    centered_query_cmd.add_argument("--base-url", required=True, help="Vespa base URL, e.g. http://localhost:8080")
    centered_query_cmd.add_argument("--config-base-url", help="Optional Vespa config server URL")
    centered_query_cmd.add_argument("--limit", type=int, default=10, help="Requested clause count")
    centered_query_cmd.add_argument("--schema", default="spec_finder", help="Vespa schema name")
    centered_query_cmd.add_argument("--namespace", default="spec_finder", help="Vespa document namespace")
    centered_query_cmd.add_argument("--registry", help="Optional query feature registry JSON")
    centered_query_cmd.add_argument("--routing-corpus", help="Optional enriched corpus JSONL used to build routing profiles")
    centered_query_cmd.add_argument("--timeout", type=float, default=30.0, help="HTTP timeout in seconds")
    centered_query_cmd.add_argument("--ranking", default="hybrid", help="Vespa ranking profile")
    centered_query_cmd.add_argument("--summary", default="short", help="Vespa summary class")
    centered_query_cmd.add_argument("--anchor-boost", type=float, default=1.15, help="Query-time anchor boost")
    centered_query_cmd.add_argument("--title-boost", type=float, default=1.2, help="Query-time title boost")
    centered_query_cmd.add_argument("--stage-boost", type=float, default=1.1, help="Query-time stage boost")
    centered_query_cmd.add_argument("--sparse-boost", type=float, default=0.0, help="Query-time sparse score boost")
    centered_query_cmd.add_argument("--vector-boost", type=float, default=1.0, help="Query-time vector boost")
    centered_query_cmd.add_argument("--embed-model", default=DEFAULT_EMBEDDING_MODEL, help="Optional embedding model for hybrid retrieval")
    centered_query_cmd.add_argument("--local-model-dir", help="Optional local Hugging Face model directory")
    centered_query_cmd.add_argument("--output-dim", type=int, help="Optional embedding output dimension")
    centered_query_cmd.add_argument("--device", default=DEFAULT_EMBEDDING_DEVICE, help="Embedding device for query vector creation")
    centered_query_cmd.add_argument("--max-length", type=int, default=2048, help="Max token length for supported models")
    centered_query_cmd.add_argument("--no-4bit", action="store_true", help="Disable 4-bit loading for supported models")
    centered_query_cmd.add_argument("--use-llm-selector", action="store_true", help="Enable OpenAI-based bounded candidate selection")
    centered_query_cmd.add_argument("--llm-relevance-only", action="store_true", help="Use LLM-only relevance selection on stage fan-out hits")
    centered_query_cmd.add_argument("--openai-model", default="gpt-4o-mini", help="OpenAI model for bounded selection")
    centered_query_cmd.add_argument("--max-retries", type=int, default=1, help="Retries for transient query errors")
    centered_query_cmd.add_argument("--retry-backoff-seconds", type=float, default=0.5, help="Linear backoff base in seconds")
    centered_query_cmd.set_defaults(func=cmd_centered_query_vespa_http)

    smoke_cmd = subparsers.add_parser("smoke-test-vespa-http", help="Run a lightweight live query smoke test against Vespa")
    smoke_cmd.add_argument("--query", required=True, help="Natural language query")
    smoke_cmd.add_argument("--base-url", required=True, help="Vespa base URL, e.g. http://localhost:8080")
    smoke_cmd.add_argument("--config-base-url", help="Optional Vespa config server URL")
    smoke_cmd.add_argument("--limit", type=int, default=5, help="Requested hit count")
    smoke_cmd.add_argument("--schema", default="spec_finder", help="Vespa schema name")
    smoke_cmd.add_argument("--namespace", default="spec_finder", help="Vespa document namespace")
    smoke_cmd.add_argument("--registry", help="Optional query feature registry JSON")
    smoke_cmd.add_argument("--timeout", type=float, default=30.0, help="HTTP timeout in seconds")
    smoke_cmd.add_argument("--ranking", default="hybrid", help="Vespa ranking profile")
    smoke_cmd.add_argument("--summary", default="short", help="Vespa summary class")
    smoke_cmd.add_argument("--sparse-boost", type=float, default=1.25, help="Query-time sparse score boost")
    smoke_cmd.add_argument("--vector-boost", type=float, default=0.45, help="Query-time vector boost")
    smoke_cmd.add_argument("--embed-model", default=DEFAULT_EMBEDDING_MODEL, help="Optional embedding model for hybrid retrieval")
    smoke_cmd.add_argument("--local-model-dir", help="Optional local Hugging Face model directory")
    smoke_cmd.add_argument("--output-dim", type=int, help="Optional embedding output dimension")
    smoke_cmd.add_argument("--device", default=DEFAULT_EMBEDDING_DEVICE, help="Embedding device for query vector creation")
    smoke_cmd.add_argument("--max-length", type=int, default=2048, help="Max token length for supported models")
    smoke_cmd.add_argument("--no-4bit", action="store_true", help="Disable 4-bit loading for supported models")
    smoke_cmd.add_argument("--stage-filter", action="append", choices=["stage2", "stage3", "else"], help="Restrict search to a stage bucket")
    smoke_cmd.set_defaults(func=cmd_smoke_test_vespa_http)

    wait_cmd = subparsers.add_parser("wait-for-vespa-http", help="Poll Vespa until query/config endpoints are reachable")
    wait_cmd.add_argument("--base-url", required=True, help="Vespa base URL, e.g. http://localhost:8080")
    wait_cmd.add_argument("--config-base-url", help="Optional Vespa config server URL")
    wait_cmd.add_argument("--schema", default="spec_finder", help="Vespa schema name")
    wait_cmd.add_argument("--namespace", default="spec_finder", help="Vespa document namespace")
    wait_cmd.add_argument("--timeout", type=float, default=60.0, help="Max wait time in seconds")
    wait_cmd.add_argument("--poll-interval", type=float, default=2.0, help="Polling interval in seconds")
    wait_cmd.add_argument("--require-config", action="store_true", help="Require config endpoint to answer as well")
    wait_cmd.set_defaults(func=cmd_wait_for_vespa_http)

    e2e_cmd = subparsers.add_parser("vespa-e2e-http", help="Run deploy, readiness wait, feed, and smoke test as one flow")
    e2e_cmd.add_argument("--base-url", required=True, help="Vespa base URL, e.g. http://localhost:8080")
    e2e_cmd.add_argument("--config-base-url", help="Optional Vespa config server URL")
    e2e_cmd.add_argument("--schema", default="spec_finder", help="Vespa schema name")
    e2e_cmd.add_argument("--namespace", default="spec_finder", help="Vespa document namespace")
    e2e_cmd.add_argument("--app-dir", default="vespa/schema", help="Application package directory")
    e2e_cmd.add_argument("--feed-input", help="Optional Vespa feed JSONL")
    e2e_cmd.add_argument("--query", help="Optional smoke test query")
    e2e_cmd.add_argument("--registry", help="Optional query feature registry JSON")
    e2e_cmd.add_argument("--limit", type=int, default=5, help="Requested hit count for smoke query")
    e2e_cmd.add_argument("--ranking", default="hybrid", help="Vespa ranking profile")
    e2e_cmd.add_argument("--summary", default="short", help="Vespa summary class")
    e2e_cmd.add_argument("--anchor-boost", type=float, default=1.15, help="Query-time anchor boost")
    e2e_cmd.add_argument("--title-boost", type=float, default=1.2, help="Query-time title boost")
    e2e_cmd.add_argument("--stage-boost", type=float, default=1.1, help="Query-time stage boost")
    e2e_cmd.add_argument("--sparse-boost", type=float, default=1.25, help="Query-time sparse score boost")
    e2e_cmd.add_argument("--vector-boost", type=float, default=0.45, help="Query-time vector boost")
    e2e_cmd.add_argument("--embed-model", default=DEFAULT_EMBEDDING_MODEL, help="Optional embedding model for hybrid retrieval")
    e2e_cmd.add_argument("--local-model-dir", help="Optional local Hugging Face model directory")
    e2e_cmd.add_argument("--output-dim", type=int, help="Optional embedding output dimension")
    e2e_cmd.add_argument("--device", default=DEFAULT_EMBEDDING_DEVICE, help="Embedding device for query vector creation")
    e2e_cmd.add_argument("--max-length", type=int, default=2048, help="Max token length for supported models")
    e2e_cmd.add_argument("--no-4bit", action="store_true", help="Disable 4-bit loading for supported models")
    e2e_cmd.add_argument("--stage-filter", action="append", choices=["stage2", "stage3", "else"], help="Restrict search to a stage bucket")
    e2e_cmd.add_argument("--deploy", action="store_true", help="Deploy application package before waiting/feeding")
    e2e_cmd.add_argument("--wait", action="store_true", help="Wait for Vespa readiness before next steps")
    e2e_cmd.add_argument("--require-config", action="store_true", help="Require config endpoint in readiness polling")
    e2e_cmd.add_argument("--deploy-timeout", type=float, default=60.0, help="Deploy timeout in seconds")
    e2e_cmd.add_argument("--ready-timeout", type=float, default=60.0, help="Readiness timeout in seconds")
    e2e_cmd.add_argument("--feed-timeout", type=float, default=30.0, help="Feed timeout in seconds")
    e2e_cmd.add_argument("--query-timeout", type=float, default=30.0, help="Smoke query timeout in seconds")
    e2e_cmd.add_argument("--poll-interval", type=float, default=2.0, help="Readiness polling interval in seconds")
    e2e_cmd.add_argument("--batch-size", type=int, default=100, help="Feed batch size")
    e2e_cmd.add_argument("--max-retries", type=int, default=2, help="Retries for deploy/feed/query transient errors")
    e2e_cmd.add_argument("--retry-backoff-seconds", type=float, default=0.5, help="Linear backoff base in seconds")
    e2e_cmd.set_defaults(func=cmd_vespa_e2e_http)

    full_cmd = subparsers.add_parser("build-full-corpus-pipeline", help="Build, enrich, embed, and export a full DOCX corpus")
    full_cmd.add_argument("inputs", nargs="+", help="Input DOCX files, directories, or glob patterns")
    full_cmd.add_argument("--corpus-output", required=True, help="Output path for raw corpus JSONL")
    full_cmd.add_argument("--enriched-output", required=True, help="Output path for enriched JSONL")
    full_cmd.add_argument("--embedded-output", required=True, help="Output path for embedded JSONL")
    full_cmd.add_argument("--vespa-output", required=True, help="Output path for Vespa feed JSONL")
    full_cmd.add_argument("--metadata", help="JSON metadata map keyed by file path or file name")
    full_cmd.add_argument("--taxonomy", help="Optional taxonomy JSON")
    full_cmd.add_argument("--model", default=DEFAULT_EMBEDDING_MODEL, help="Embedding model, e.g. hash-16 or qwen3-embedding-0.6b")
    full_cmd.add_argument("--local-model-dir", help="Optional local Hugging Face model directory")
    full_cmd.add_argument("--output-dim", type=int, help="Optional embedding output dimension")
    full_cmd.add_argument("--device", default=DEFAULT_EMBEDDING_DEVICE, help="Embedding device, e.g. cuda or cpu")
    full_cmd.add_argument("--batch-size", type=int, default=4, help="Embedding batch size")
    full_cmd.add_argument("--offset", type=int, default=0, help="Start offset in the enriched JSONL")
    full_cmd.add_argument("--limit", type=int, help="Optional maximum number of records to embed")
    full_cmd.add_argument("--max-length", type=int, default=2048, help="Max token length for supported models")
    full_cmd.add_argument("--no-4bit", action="store_true", help="Disable 4-bit loading for supported models")
    full_cmd.set_defaults(func=cmd_build_full_corpus_pipeline)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
