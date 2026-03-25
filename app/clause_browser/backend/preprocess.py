from __future__ import annotations

import argparse
import hashlib
import json
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
) -> int:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    media_root = Path(media_dir)
    media_root.mkdir(parents=True, exist_ok=True)
    converted_root = media_root / ".converted_docx"

    clause_parser = DocxClauseParser()
    rich_parser = RichDocxClauseParser(media_root=media_root)
    count = 0

    with output.open("w", encoding="utf-8") as handle:
        for source in expand_docx_inputs(inputs):
            source_path = Path(source)
            parse_path = resolve_parse_path(source_path, converted_root)
            metadata = SpecMetadata(**derive_metadata_hints(source_path))
            clause_records = [record for record in clause_parser.parse(parse_path, metadata) if record.doc_type == "clause_doc"]
            if not clause_records:
                continue

            spec_no = clause_records[0].spec_no
            spec_title = clause_records[0].spec_title
            rich_nodes = rich_parser.parse_document(spec_no=spec_no, spec_title=spec_title, source_file=str(parse_path))

            merged: dict[str, dict[str, Any]] = {}
            for clause in clause_records:
                node = rich_nodes.get(clause.clause_id)
                merged[clause.clause_id] = {
                    "spec_no": clause.spec_no,
                    "spec_title": clause.spec_title,
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

            for clause in sorted(merged.values(), key=lambda item: (item["order_in_source"], item["clause_id"])):
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
    parser.add_argument("--media-dir", default="artifacts/clause_browser_media")
    args = parser.parse_args()

    count = build_clause_browser_corpus(inputs=args.inputs, output_path=args.output, media_dir=args.media_dir)
    print(f"Wrote {count} browser clause records to {args.output}")


if __name__ == "__main__":
    main()
