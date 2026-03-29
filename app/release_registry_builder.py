from __future__ import annotations

import argparse
import json
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Iterable

from retrieval.query_normalizer import QueryFeatureRegistry, build_query_feature_registry_from_corpus


def iter_json_dicts(path: str | Path) -> Iterable[dict]:
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def merge_records_by_doc_id(input_paths: Iterable[str | Path]) -> list[dict]:
    merged: dict[str, dict] = {}
    for input_path in input_paths:
        path = Path(input_path)
        if not path.exists():
            continue
        for record in iter_json_dicts(path):
            doc_id = str(record.get("doc_id") or "").strip()
            if not doc_id:
                continue
            merged[doc_id] = record
    return list(merged.values())


def registry_group_key(record: dict) -> tuple[str, str]:
    release_data = str(record.get("release_data") or "unknown-date").strip() or "unknown-date"
    release = str(record.get("release") or "unknown-release").strip() or "unknown-release"
    return release_data, release


def write_jsonl_dicts(records: Iterable[dict], path: str | Path) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=True) + "\n")


def build_registry_from_records(records: list[dict]) -> QueryFeatureRegistry:
    with tempfile.TemporaryDirectory(prefix="specbot-registry-") as temp_dir:
        temp_path = Path(temp_dir) / "records.jsonl"
        write_jsonl_dicts(records, temp_path)
        return build_query_feature_registry_from_corpus(temp_path)


def write_release_registries(
    *,
    input_paths: Iterable[str | Path],
    global_output: str | Path,
    output_root: str | Path,
) -> dict[str, int]:
    merged_records = merge_records_by_doc_id(input_paths)
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for record in merged_records:
        grouped[registry_group_key(record)].append(record)

    global_registry = build_registry_from_records(merged_records)
    global_output_path = Path(global_output)
    global_output_path.parent.mkdir(parents=True, exist_ok=True)
    global_output_path.write_text(json.dumps(global_registry.to_dict(), ensure_ascii=True, indent=2), encoding="utf-8")

    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    for (release_data, release), records in grouped.items():
        registry = build_registry_from_records(records)
        target = root / release_data / release / "spec_query_registry.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(registry.to_dict(), ensure_ascii=True, indent=2), encoding="utf-8")

    return {
        "merged_records": len(merged_records),
        "group_count": len(grouped),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build global and release-scoped query registries")
    parser.add_argument("--inputs", nargs="+", required=True, help="One or more enriched corpus JSONL files")
    parser.add_argument("--global-output", required=True, help="Output path for the global registry JSON")
    parser.add_argument("--output-root", required=True, help="Root directory for release-scoped registries")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    summary = write_release_registries(
        input_paths=args.inputs,
        global_output=args.global_output,
        output_root=args.output_root,
    )
    print(json.dumps(summary, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
