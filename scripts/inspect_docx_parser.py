#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from docx import Document
from docx.text.paragraph import Paragraph

from parser.docx_clause_parser import (
    DocxClauseParser,
    SpecMetadata,
    iter_block_items,
    normalize_whitespace,
    paragraph_style_level,
    should_treat_paragraph_as_heading,
    split_clause_heading,
)


@dataclass
class TraceClause:
    clause_id: str
    clause_path: list[str]
    level: int


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Parse a single DOCX file with DocxClauseParser and print inspectable JSON output."
    )
    parser.add_argument("input", help="Path to the DOCX file to inspect")
    parser.add_argument("--spec-no", default="", help="Optional spec number override")
    parser.add_argument("--spec-title", default="", help="Optional spec title override")
    parser.add_argument("--release", default="", help="Optional release override")
    parser.add_argument("--release-data", default="", help="Optional release data override")
    parser.add_argument("--stage-hint", default="", help="Optional stage hint override")
    parser.add_argument(
        "--doc-type",
        default="clause_doc",
        choices=["clause_doc", "passage_doc", "table_doc", "table_row_doc", "entity_doc", "all"],
        help="Which doc_type to print",
    )
    parser.add_argument("--clause-id", default="", help="Only print records for one clause_id")
    parser.add_argument("--limit", type=int, default=0, help="Optional max record count to print")
    parser.add_argument(
        "--full-text",
        action="store_true",
        help="Include full text in output. Default prints only a short preview.",
    )
    parser.add_argument(
        "--trace",
        action="store_true",
        help="Print heading-resolution trace instead of parsed records.",
    )
    return parser


def resolve_heading(clause_counter: int, text: str, heading_level: int | None, heading: tuple[str, str] | None) -> tuple[str, str, int]:
    if heading:
        clause_id, clause_title = heading
        if clause_id.startswith("Annex "):
            level = 1
        else:
            level = clause_id.count(".") + 1
        return clause_id, clause_title, level
    clause_id = f"heading_{clause_counter}"
    clause_title = text
    level = heading_level or 1
    return clause_id, clause_title, level


def build_trace(source: Path) -> dict[str, object]:
    document = Document(str(source))
    clause_stack: list[TraceClause] = []
    clause_counter = 0
    paragraph_counter = 0
    events: list[dict[str, object]] = []

    for block in iter_block_items(document):
        if not isinstance(block, Paragraph):
            continue
        text = normalize_whitespace(block.text)
        style_name = block.style.name if block.style else ""
        if not text or style_name.lower().startswith("toc"):
            continue

        heading_level = paragraph_style_level(style_name)
        parsed_heading = split_clause_heading(text)
        heading = parsed_heading if should_treat_paragraph_as_heading(text, heading_level, parsed_heading) else None
        if heading_level is None and heading is None:
            continue

        clause_counter += 1
        paragraph_counter += 1
        stack_before = [item.clause_id for item in clause_stack]
        clause_id, clause_title, level = resolve_heading(clause_counter, text, heading_level, heading)
        if clause_id and clause_id[0].isdigit():
            while clause_stack and clause_stack[-1].clause_id.startswith("Annex "):
                clause_stack.pop()
        while clause_stack and clause_stack[-1].level >= level:
            clause_stack.pop()
        clause_path = [*clause_stack[-1].clause_path, clause_id] if clause_stack else [clause_id]
        parent_clause_id = clause_stack[-1].clause_id if clause_stack else ""
        clause_stack.append(TraceClause(clause_id=clause_id, clause_path=clause_path, level=level))
        events.append(
            {
                "paragraph_index": paragraph_counter,
                "style_name": style_name,
                "heading_level_from_style": heading_level,
                "text": text,
                "parsed_heading": {
                    "clause_id": parsed_heading[0],
                    "clause_title": parsed_heading[1],
                } if parsed_heading else None,
                "accepted_as_heading": heading is not None or heading_level is not None,
                "resolved_clause_id": clause_id,
                "resolved_clause_title": clause_title,
                "resolved_level": level,
                "parent_clause_id": parent_clause_id,
                "clause_path": clause_path,
                "stack_before": stack_before,
                "stack_after": [item.clause_id for item in clause_stack],
            }
        )

    return {
        "input": str(source),
        "trace_event_count": len(events),
        "events": events,
    }


def main() -> None:
    args = build_parser().parse_args()
    source = Path(args.input)
    if args.trace:
        print(json.dumps(build_trace(source), ensure_ascii=False, indent=2))
        return
    metadata = SpecMetadata(
        spec_no=args.spec_no,
        spec_title=args.spec_title,
        release=args.release,
        release_data=args.release_data,
        stage_hint=args.stage_hint,
        source_file=str(source),
    )
    parser = DocxClauseParser()
    records = parser.parse(source, metadata)

    filtered = []
    for record in records:
        if args.doc_type != "all" and record.doc_type != args.doc_type:
            continue
        if args.clause_id and record.clause_id != args.clause_id:
            continue
        payload = {
            "doc_id": record.doc_id,
            "doc_type": record.doc_type,
            "spec_no": record.spec_no,
            "stage_hint": record.stage_hint,
            "clause_id": record.clause_id,
            "parent_clause_id": record.parent_clause_id,
            "clause_path": record.clause_path,
            "clause_title": record.clause_title,
            "source_file": record.source_file,
            "order_in_source": record.order_in_source,
        }
        if args.full_text:
            payload["text"] = record.text
        else:
            payload["text_preview"] = record.text[:300]
        filtered.append(payload)

    if args.limit > 0:
        filtered = filtered[: args.limit]

    output = {
        "input": str(source),
        "record_count": len(records),
        "printed_count": len(filtered),
        "doc_type_filter": args.doc_type,
        "clause_id_filter": args.clause_id,
        "records": filtered,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
