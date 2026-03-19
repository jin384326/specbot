from __future__ import annotations

from pathlib import Path

from parser.corpus_builder import expand_docx_inputs


def test_expand_docx_inputs_supports_directories_and_globs(tmp_path: Path) -> None:
    rel18 = tmp_path / "Specs" / "2025-12" / "Rel-18"
    rel19 = tmp_path / "Specs" / "2026-03" / "Rel-19"
    rel18.mkdir(parents=True)
    rel19.mkdir(parents=True)
    first = rel18 / "23501-a.docx"
    second = rel19 / "23502-b.docx"
    ignored = rel19 / "notes.txt"
    first.write_text("", encoding="utf-8")
    second.write_text("", encoding="utf-8")
    ignored.write_text("", encoding="utf-8")

    discovered = expand_docx_inputs([rel18.parent.parent, str(rel19 / "*.docx")])

    assert discovered == [first, second]
