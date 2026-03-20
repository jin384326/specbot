from __future__ import annotations

import zipfile
from pathlib import Path


DOCX_SUFFIX = ".docx"


def extract_docx_from_zip(
    zip_path: str | Path,
    output_dir: str | Path,
    *,
    flatten: bool = False,
) -> list[Path]:
    """Extract all .docx members from a zip into output_dir.

    Args:
        zip_path: Path to the zip file.
        output_dir: Directory to extract into (created if needed).
        flatten: If True, extract all docx to output_dir with basename only
                 (may overwrite if same name in different zip folders).
                 If False, preserve relative path inside zip.

    Returns:
        List of extracted file paths.
    """
    zip_path = Path(zip_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    extracted: list[Path] = []

    with zipfile.ZipFile(zip_path, "r") as zf:
        for name in zf.namelist():
            if name.endswith("/") or not name.lower().endswith(DOCX_SUFFIX):
                continue
            # Avoid path traversal
            clean = Path(name).as_posix()
            if ".." in clean or clean.startswith("/"):
                continue
            if flatten:
                target = output_dir / Path(name).name
            else:
                target = output_dir / clean
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(zf.read(name))
            extracted.append(target)

    return extracted
