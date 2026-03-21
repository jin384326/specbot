from __future__ import annotations

from pathlib import Path

from docx import Document

from parser.corpus_builder import build_corpus, expand_docx_inputs


def write_docx(path: Path, text: str = "1 Scope") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = Document()
    doc.add_paragraph(text, style="Heading 1")
    doc.save(path)


def write_fake_legacy_doc(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes.fromhex("D0CF11E0A1B11AE1") + b"legacy-word-doc")


def test_expand_docx_inputs_supports_directories_globs_and_doc_files(tmp_path: Path) -> None:
    rel18 = tmp_path / "Specs" / "2025-12" / "Rel-18"
    rel19 = tmp_path / "Specs" / "2026-03" / "Rel-19"
    first = rel18 / "23501-a.docx"
    second = rel19 / "23502-b.doc"
    ignored = rel19 / "notes.txt"

    write_docx(first)
    write_fake_legacy_doc(second)
    ignored.parent.mkdir(parents=True, exist_ok=True)
    ignored.write_text("", encoding="utf-8")

    discovered = expand_docx_inputs([rel18.parent.parent, str(rel19 / "*.doc")])

    assert discovered == [first, second]


def test_build_corpus_converts_legacy_word_documents_before_parse(tmp_path: Path, monkeypatch) -> None:
    legacy_doc = tmp_path / "Specs" / "2025-12" / "Rel-18" / "29512-i90.doc"
    converted_docx = tmp_path / "converted" / "29512-i90.docx"
    output_path = tmp_path / "artifact" / "corpus.jsonl"
    write_fake_legacy_doc(legacy_doc)
    write_docx(converted_docx)

    calls: list[Path] = []

    class StubParser:
        def parse(self, path: str | Path, metadata=None) -> list:
            calls.append(Path(path))
            return []

    def fake_convert(source: str | Path, converted_root: str | Path) -> Path | None:
        assert Path(source) == legacy_doc
        assert Path(converted_root) == output_path.parent / ".converted_docx"
        return converted_docx

    monkeypatch.setattr("parser.corpus_builder.convert_word_to_docx", fake_convert)

    count = build_corpus([legacy_doc], output_path, parser=StubParser())

    assert count == 0
    assert calls == [converted_docx]


def test_build_corpus_skips_unconvertible_legacy_word_documents(
    tmp_path: Path,
    monkeypatch,
) -> None:
    legacy_doc = tmp_path / "Specs" / "2025-12" / "Rel-18" / "29512-i90.docx"
    output_path = tmp_path / "artifact" / "corpus.jsonl"
    write_fake_legacy_doc(legacy_doc)

    class StubParser:
        def parse(self, path: str | Path, metadata=None) -> list:
            raise AssertionError("parse should not be called for skipped inputs")

    monkeypatch.setattr("parser.corpus_builder.convert_word_to_docx", lambda source, converted_root: None)

    count = build_corpus([legacy_doc], output_path, parser=StubParser())

    assert count == 0
