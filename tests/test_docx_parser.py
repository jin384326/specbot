from __future__ import annotations

from pathlib import Path

from docx import Document

from parser.docx_clause_parser import (
    DocxClauseParser,
    SpecMetadata,
    clean_table_matrix,
    split_clause_heading,
    table_to_linearized_text,
)


def build_sample_doc(path: Path) -> None:
    doc = Document()
    cover = doc.add_table(rows=3, cols=1)
    cover.cell(0, 0).text = "3GPP TS 23.501 V18.12.0 (2025-12)"
    cover.cell(1, 0).text = "Technical Specification"
    cover.cell(2, 0).text = (
        "3rd Generation Partnership Project; "
        "Technical Specification Group Services and System Aspects; "
        "System architecture for the 5G System (5GS); "
        "Stage 2 (Release 18)"
    )
    doc.add_paragraph("1 Scope", style="Heading 1")
    doc.add_paragraph("This clause introduces the scope.")
    doc.add_paragraph("This clause also references 3GPP TS 23.502 and clause 4.2.1.")
    doc.add_paragraph("2 Architecture", style="Heading 1")
    for idx in range(6):
        doc.add_paragraph(f"Paragraph {idx} describing session management and access control.")
    table = doc.add_table(rows=3, cols=2)
    table.cell(0, 0).text = "Parameter"
    table.cell(0, 1).text = "Value"
    table.cell(1, 0).text = "SSC mode"
    table.cell(1, 1).text = "1"
    table.cell(2, 0).text = "Always-on PDU"
    table.cell(2, 1).text = "Supported"
    doc.save(path)


def test_clause_heading_parsing(tmp_path: Path) -> None:
    source = tmp_path / "2025-12" / "Rel-18" / "23501-test.docx"
    source.parent.mkdir(parents=True)
    build_sample_doc(source)
    parser = DocxClauseParser()
    records = parser.parse(source, SpecMetadata(spec_no="23501", spec_title="System architecture"))

    clause_docs = [record for record in records if record.doc_type == "clause_doc"]
    assert [record.clause_id for record in clause_docs] == ["1", "2"]
    assert clause_docs[0].clause_title == "Scope"
    assert clause_docs[1].clause_title == "Architecture"


def test_table_matrix_and_linearized_text(tmp_path: Path) -> None:
    source = tmp_path / "table.docx"
    build_sample_doc(source)
    doc = Document(source)
    matrix = clean_table_matrix(doc.tables[1])
    assert matrix[0] == ["Parameter", "Value"]
    linearized = table_to_linearized_text(matrix, "Architecture")
    assert "row 1: Parameter: SSC mode; Value: 1" in linearized
    assert "Table Architecture" in linearized


def test_passage_splitting(tmp_path: Path) -> None:
    source = tmp_path / "passages.docx"
    build_sample_doc(source)
    parser = DocxClauseParser(passage_char_limit=90, passage_paragraph_limit=2, min_passage_chars=10)
    records = parser.parse(source, SpecMetadata(spec_no="23501"))

    passages = [record for record in records if record.doc_type == "passage_doc" and record.clause_id == "2"]
    assert len(passages) >= 2
    assert passages[0].paragraph_start_index <= passages[0].paragraph_end_index


def test_annex_heading_and_false_positive_guard() -> None:
    assert split_clause_heading("Annex A (informative) Example flows") == ("Annex A", "Example flows")
    assert split_clause_heading("5G architecture") is None


def test_spec_title_and_release_data_are_inferred_from_docx_and_path(tmp_path: Path) -> None:
    source = tmp_path / "2025-12" / "Rel-18" / "23501-demo.docx"
    source.parent.mkdir(parents=True)
    build_sample_doc(source)
    parser = DocxClauseParser()
    records = parser.parse(source, SpecMetadata(spec_no="23501"))

    first_clause = next(record for record in records if record.doc_type == "clause_doc")
    assert first_clause.spec_title == "System architecture for the 5G System (5GS); Stage 2 (Release 18)"
    assert first_clause.release_data == "2025-12"
    assert first_clause.stage_hint == "Stage 2"


def test_unknown_stage_is_marked_as_else(tmp_path: Path) -> None:
    source = tmp_path / "unknown-stage.docx"
    doc = Document()
    cover = doc.add_table(rows=3, cols=1)
    cover.cell(0, 0).text = "3GPP TS 29.999 V1.0.0 (2025-12)"
    cover.cell(1, 0).text = "Technical Specification"
    cover.cell(2, 0).text = "Some specification without explicit stage"
    doc.add_paragraph("1 Scope", style="Heading 1")
    doc.add_paragraph("Body text")
    doc.save(source)

    parser = DocxClauseParser()
    records = parser.parse(source, SpecMetadata(spec_no="29999"))

    first_clause = next(record for record in records if record.doc_type == "clause_doc")
    assert first_clause.stage_hint == "else"


def test_parser_skips_annex_and_change_history_sections(tmp_path: Path) -> None:
    source = tmp_path / "skip-annex.docx"
    doc = Document()
    cover = doc.add_table(rows=3, cols=1)
    cover.cell(0, 0).text = "3GPP TS 23.501 V18.12.0 (2025-12)"
    cover.cell(1, 0).text = "Technical Specification"
    cover.cell(2, 0).text = "System architecture for the 5G System (5GS); Stage 2 (Release 18)"
    doc.add_paragraph("1 Scope", style="Heading 1")
    doc.add_paragraph("Normal body text.")
    doc.add_paragraph("Annex A (informative) Example flows", style="Heading 1")
    doc.add_paragraph("This annex should not become a corpus record.")
    doc.add_paragraph("Annex B (informative) Change history", style="Heading 1")
    doc.add_paragraph("This change history should not become a corpus record.")
    doc.save(source)

    parser = DocxClauseParser()
    records = parser.parse(source, SpecMetadata(spec_no="23501"))

    clause_titles = [record.clause_title for record in records if record.doc_type == "clause_doc"]
    assert clause_titles == ["Scope"]
