from __future__ import annotations

import glob
import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Iterable

from parser.docx_clause_parser import DocxClauseParser, SpecMetadata
from parser.models import DocRecord

OLE_MAGIC = bytes.fromhex("D0CF11E0A1B11AE1")


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


def is_supported_docx(path: str | Path) -> bool:
    candidate = Path(path)
    return candidate.is_file() and candidate.suffix.lower() == ".docx" and zipfile.is_zipfile(candidate)


def is_legacy_word_document(path: str | Path) -> bool:
    candidate = Path(path)
    if not candidate.is_file():
        return False
    try:
        with candidate.open("rb") as handle:
            return handle.read(len(OLE_MAGIC)) == OLE_MAGIC
    except OSError:
        return False


def find_office_converter() -> str | None:
    for candidate in ("soffice", "libreoffice", "lowriter"):
        executable = shutil.which(candidate)
        if executable:
            return executable
    return None


def convert_word_to_docx(source_path: str | Path, converted_root: str | Path) -> Path | None:
    source = Path(source_path)
    converter = find_office_converter()
    if converter is None:
        print(
            f"Skipping Word document without converter installed: {source} "
            "(install LibreOffice/soffice to enable auto-conversion)",
            file=sys.stderr,
        )
        return None

    digest = hashlib.sha1(str(source.resolve()).encode("utf-8")).hexdigest()[:12]
    output_dir = Path(converted_root) / digest
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        subprocess.run(
            [converter, "--headless", "--convert-to", "docx", "--outdir", str(output_dir), str(source)],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = exc.stderr.strip() if isinstance(exc, subprocess.CalledProcessError) and exc.stderr else str(exc)
        print(f"Skipping Word document after conversion failure: {source} ({detail})", file=sys.stderr)
        return None

    converted = output_dir / f"{source.stem}.docx"
    if not is_supported_docx(converted):
        print(f"Skipping Word document with missing converted DOCX output: {source}", file=sys.stderr)
        return None
    return converted


def expand_docx_inputs(inputs: Iterable[str | Path], recursive: bool = True) -> list[Path]:
    discovered: list[Path] = []
    seen: set[Path] = set()
    for item in inputs:
        path = Path(item)
        matches: list[Path]
        if any(char in str(item) for char in ["*", "?", "["]):
            matches = [Path(candidate) for candidate in glob.glob(str(item), recursive=recursive) if Path(candidate).is_file()]
        elif path.is_dir():
            patterns = ("*.docx", "*.doc")
            matches = []
            for pattern in patterns:
                iterator = path.rglob(pattern) if recursive else path.glob(pattern)
                matches.extend(candidate for candidate in iterator if candidate.is_file())
        else:
            matches = [path]
        for match in sorted(matches):
            if not match.is_file():
                print(f"Skipping missing Word input: {match}", file=sys.stderr)
                continue
            resolved = match.resolve()
            if resolved in seen or match.suffix.lower() not in {".docx", ".doc"}:
                continue
            seen.add(resolved)
            discovered.append(match)
    return discovered


def prepare_corpus_inputs(
    inputs: Iterable[str | Path],
    output_path: str | Path,
    recursive: bool = True,
) -> list[tuple[Path, Path]]:
    converted_root = Path(output_path).parent / ".converted_docx"
    prepared: list[tuple[Path, Path]] = []
    for path in expand_docx_inputs(inputs, recursive=recursive):
        if is_supported_docx(path):
            prepared.append((path, path))
            continue
        if is_legacy_word_document(path):
            converted = convert_word_to_docx(path, converted_root)
            if converted is not None:
                prepared.append((path, converted))
            continue
        print(f"Skipping unsupported Word container: {path}", file=sys.stderr)
    return prepared


def derive_metadata_hints(path: str | Path) -> dict[str, str]:
    source = Path(path)
    hints: dict[str, str] = {"source_file": str(source)}
    digits = source.stem[:5]
    if digits.isdigit():
        hints["spec_no"] = digits
        hints["series"] = digits[:2]
        hints["ts_or_tr"] = "TS"
    for part in source.parts:
        if part.startswith("Rel-"):
            hints["release"] = part
            break
    for part in source.parts:
        if len(part) == 7 and part[4] == "-" and part[:4].isdigit() and part[5:].isdigit():
            hints["release_data"] = part
            break
    version = source.stem.rsplit("-", maxsplit=1)
    if len(version) == 2:
        suffix = version[1]
        if len(suffix) >= 2 and suffix[0].isalpha() and suffix[1:].isdigit():
            hints["version_tag"] = suffix
    return hints


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
    for source_path, parse_path in prepare_corpus_inputs(docx_paths, output_path):
        metadata = metadata_map.get(str(source_path), metadata_map.get(source_path.name))
        metadata_payload = dict(metadata or {})
        for key, value in derive_metadata_hints(source_path).items():
            metadata_payload.setdefault(key, value)
        records = active_parser.parse(parse_path, metadata=metadata_payload)
        write_jsonl(records, output_path, append=append or count > 0)
        count += len(records)
    return count
