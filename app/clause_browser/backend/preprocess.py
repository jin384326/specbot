from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from parser.corpus_builder import (
    convert_word_to_docx,
    derive_metadata_hints,
    expand_docx_inputs,
    is_legacy_word_document,
    is_supported_docx,
)
from parser.docx_clause_parser import DocxClauseParser, SpecMetadata

from app.clause_browser.backend.render_parser import RichDocxClauseParser


def build_clause_browser_corpus(
    *,
    inputs: list[str],
    output_path: str | Path,
    media_dir: str | Path,
    workers: int = 1,
) -> int:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    media_root = Path(media_dir)
    media_root.mkdir(parents=True, exist_ok=True)
    converted_root = media_root / ".converted_docx"

    count = 0

    with output.open("w", encoding="utf-8") as handle:
        sources = expand_docx_inputs(inputs)
        worker_count = max(1, int(workers))
        if worker_count == 1:
            processed_sources = (
                _process_source_for_clause_browser(source_path=Path(source), media_dir=media_root)
                for source in sources
            )
        else:
            with concurrent.futures.ProcessPoolExecutor(max_workers=worker_count) as executor:
                processed_sources = executor.map(
                    _process_source_for_clause_browser,
                    [Path(source) for source in sources],
                    [media_root for _ in sources],
                )

        for merged_values in processed_sources:
            for clause in merged_values:
                handle.write(
                    json.dumps(
                        {
                            "doc_type": "clause_doc",
                            "content_kind": "clause",
                            "doc_id": f'{clause["spec_no"]}:clause:{clause["clause_id"]}',
                            **clause,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                count += 1

    return count


def group_sources_by_release(inputs: list[str]) -> dict[tuple[str, str], list[str]]:
    grouped: dict[tuple[str, str], list[str]] = {}
    for source in expand_docx_inputs(inputs):
        hints = derive_metadata_hints(source)
        release_data = hints.get("release_data") or "unknown-date"
        release = hints.get("release") or "unknown-release"
        grouped.setdefault((release_data, release), []).append(str(source))
    return grouped


def build_clause_browser_corpora_by_release(
    *,
    inputs: list[str],
    output_root: str | Path,
    media_dir: str | Path,
    workers: int = 1,
) -> dict[str, int]:
    output_base = Path(output_root)
    output_base.mkdir(parents=True, exist_ok=True)
    summary: dict[str, int] = {}
    for (release_data, release), grouped_inputs in sorted(group_sources_by_release(inputs).items()):
        output_path = output_base / release_data / release / "clause_browser_corpus.jsonl"
        count = build_clause_browser_corpus(
            inputs=grouped_inputs,
            output_path=output_path,
            media_dir=media_dir,
            workers=workers,
        )
        summary[f"{release_data}/{release}"] = count
    return summary


def _process_source_for_clause_browser(source_path: Path, media_dir: str | Path) -> list[dict[str, Any]]:
    media_root = Path(media_dir)
    converted_root = media_root / ".converted_docx"
    clause_parser = DocxClauseParser()
    rich_parser = RichDocxClauseParser(media_root=media_root)

    parse_path = resolve_parse_path(source_path, converted_root)
    metadata = SpecMetadata(**derive_metadata_hints(source_path))
    clause_records = [record for record in clause_parser.parse(parse_path, metadata) if record.doc_type == "clause_doc"]
    if not clause_records:
        return []

    spec_no = clause_records[0].spec_no
    spec_title = clause_records[0].spec_title
    rich_nodes = rich_parser.parse_document(spec_no=spec_no, spec_title=spec_title, source_file=str(parse_path))

    merged: dict[str, dict[str, Any]] = {}
    for clause in clause_records:
        node = rich_nodes.get(clause.clause_id)
        merged[clause.clause_id] = {
            "spec_no": clause.spec_no,
            "spec_title": clause.spec_title,
            "release": clause.release,
            "release_data": clause.release_data,
            "clause_id": clause.clause_id,
            "clause_title": clause.clause_title,
            "parent_clause_id": clause.parent_clause_id,
            "clause_path": list(clause.clause_path),
            "text": clause.text,
            "source_file": str(parse_path),
            "order_in_source": clause.order_in_source,
            "blocks": node.blocks if node and node.blocks else fallback_blocks(clause.text),
        }

    for clause_id, node in rich_nodes.items():
        if clause_id in merged:
            if node.blocks:
                merged[clause_id]["blocks"] = node.blocks
            continue
        merged[clause_id] = {
            "spec_no": node.spec_no,
            "spec_title": node.spec_title,
            "release": metadata.release,
            "release_data": metadata.release_data,
            "clause_id": node.clause_id,
            "clause_title": node.clause_title,
            "parent_clause_id": node.parent_clause_id,
            "clause_path": list(node.clause_path),
            "text": "\n".join(block["text"] for block in node.blocks if block["type"] == "paragraph").strip(),
            "source_file": node.source_file,
            "order_in_source": node.order_in_source,
            "blocks": node.blocks,
        }

    synthesize_missing_ancestors(merged)
    return sorted(merged.values(), key=lambda item: (item["order_in_source"], item["clause_id"]))


def resolve_parse_path(source_path: Path, converted_root: Path) -> Path:
    if is_supported_docx(source_path):
        return source_path
    if is_legacy_word_document(source_path):
        existing_converted = expected_converted_path(source_path, converted_root)
        if existing_converted.exists():
            return existing_converted
        converted = convert_word_to_docx(source_path, converted_root)
        if converted is None and existing_converted.exists():
            return existing_converted
        if converted is None:
            raise FileNotFoundError(f"Unable to convert {source_path}")
        return converted
    if source_path.with_suffix(".docx").exists():
        return source_path.with_suffix(".docx")
    raise FileNotFoundError(f"Unsupported source: {source_path}")


def fallback_blocks(text: str) -> list[dict[str, Any]]:
    return [{"type": "paragraph", "text": paragraph.strip()} for paragraph in text.splitlines() if paragraph.strip()]


def expected_converted_path(source_path: Path, converted_root: Path) -> Path:
    digest = hashlib.sha1(str(source_path.resolve()).encode("utf-8")).hexdigest()[:12]
    return converted_root / digest / f"{source_path.stem}.docx"


def synthesize_missing_ancestors(merged: dict[str, dict[str, Any]]) -> None:
    for clause in list(merged.values()):
        path = clause.get("clause_path") or []
        for index, ancestor_id in enumerate(path[:-1]):
            if ancestor_id in merged:
                continue
            parent_clause_id = path[index - 1] if index > 0 else ""
            merged[ancestor_id] = {
                "spec_no": clause["spec_no"],
                "spec_title": clause["spec_title"],
                "release": clause.get("release", ""),
                "release_data": clause.get("release_data", ""),
                "clause_id": ancestor_id,
                "clause_title": ancestor_id,
                "parent_clause_id": parent_clause_id,
                "clause_path": path[: index + 1],
                "text": "",
                "source_file": clause["source_file"],
                "order_in_source": max(0, clause["order_in_source"] - (len(path) - index)),
                "blocks": [],
            }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build clause browser corpus with paragraph/table/image blocks.")
    parser.add_argument("--inputs", nargs="+", default=["Specs"])
    parser.add_argument("--output", default="artifacts/clause_browser_corpus.jsonl")
    parser.add_argument("--output-root", default="artifacts/clause_browser_corpora")
    parser.add_argument("--media-dir", default="artifacts/clause_browser_media")
    parser.add_argument("--workers", type=int, default=max(1, os.cpu_count() or 1))
    args = parser.parse_args()

    count = build_clause_browser_corpus(inputs=args.inputs, output_path=args.output, media_dir=args.media_dir, workers=args.workers)
    grouped_summary = build_clause_browser_corpora_by_release(
        inputs=args.inputs,
        output_root=args.output_root,
        media_dir=args.media_dir,
        workers=args.workers,
    )
    print(f"Wrote {count} browser clause records to {args.output}")
    print(json.dumps({"grouped_outputs": grouped_summary}, ensure_ascii=False))


if __name__ == "__main__":
    main()
