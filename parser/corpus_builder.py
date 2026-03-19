from __future__ import annotations

import glob
import json
from pathlib import Path
from typing import Iterable

from parser.docx_clause_parser import DocxClauseParser, SpecMetadata
from parser.models import DocRecord


def write_jsonl(records: Iterable[DocRecord], output_path: str | Path, append: bool = True) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append else "w"
    with path.open(mode, encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record.to_dict(), ensure_ascii=True) + "\n")


def parse_single_docx(
    docx_path: str | Path,
    metadata: SpecMetadata | dict | None = None,
    parser: DocxClauseParser | None = None,
) -> list[DocRecord]:
    active_parser = parser or DocxClauseParser()
    return active_parser.parse(docx_path, metadata=metadata)


def expand_docx_inputs(inputs: Iterable[str | Path], recursive: bool = True) -> list[Path]:
    discovered: list[Path] = []
    seen: set[Path] = set()
    for item in inputs:
        path = Path(item)
        matches: list[Path]
        if any(char in str(item) for char in ["*", "?", "["]):
            matches = [Path(candidate) for candidate in glob.glob(str(item), recursive=recursive) if Path(candidate).is_file()]
        elif path.is_dir():
            iterator = path.rglob("*.docx") if recursive else path.glob("*.docx")
            matches = [candidate for candidate in iterator if candidate.is_file()]
        else:
            matches = [path]
        for match in sorted(matches):
            resolved = match.resolve()
            if resolved in seen or match.suffix.lower() != ".docx":
                continue
            seen.add(resolved)
            discovered.append(match)
    return discovered


def build_corpus(
    docx_paths: Iterable[str | Path],
    output_path: str | Path,
    metadata_by_source: dict[str, dict] | None = None,
    append: bool = True,
    parser: DocxClauseParser | None = None,
) -> int:
    metadata_map = metadata_by_source or {}
    active_parser = parser or DocxClauseParser()
    count = 0
    for docx_path in expand_docx_inputs(docx_paths):
        path = Path(docx_path)
        metadata = metadata_map.get(str(path), metadata_map.get(path.name))
        records = active_parser.parse(path, metadata=metadata)
        write_jsonl(records, output_path, append=append or count > 0)
        count += len(records)
    return count
