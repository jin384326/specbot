from __future__ import annotations

from pathlib import Path

from docx import Document

from parser.docx_clause_parser import (
    DocxClauseParser,
    SpecMetadata,
    clean_table_matrix,
    dedupe_duplicate_cell_texts_preserve_order,
    dedupe_duplicate_brackets,
    dedupe_repeated_lines_and_semicolon_lists,
    linearized_row_pairs,
    normalize_table_cell_text,
    remove_redundant_brackets_matching_outside,
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


def test_dedupe_duplicate_brackets_in_cell() -> None:
    assert dedupe_duplicate_brackets("a [PDU Session request] b [PDU Session request]") == "a [PDU Session request] b"
    assert dedupe_duplicate_brackets("[] []") == "[]"


def test_remove_redundant_brackets_when_repeated_outside() -> None:
    assert (
        normalize_table_cell_text("PDU Session Establishment Request [PDU Session Establishment Request]")
        == "PDU Session Establishment Request"
    )


def test_linearized_row_skips_consecutive_duplicate_merged_cells() -> None:
    header = ["Message", "Message", "Direction"]
    row = ["Foo request", "Foo request", "UE to CN"]
    pairs = linearized_row_pairs(header, row)
    assert pairs == [("Message", "Foo request"), ("Direction", "UE to CN")]


def test_dedupe_semicolon_and_line_repetition_in_list_like_cell() -> None:
    cell = (
        "PDU Session Establishment Request; PDU Session Establishment Request; "
        "PDU Session Modification Request"
    )
    assert (
        dedupe_repeated_lines_and_semicolon_lists(cell)
        == "PDU Session Establishment Request; PDU Session Modification Request"
    )
    multiline = "The SMF shall send X.\nThe SMF shall send X.\nThe AMF shall receive Y."
    out = dedupe_repeated_lines_and_semicolon_lists(multiline, min_line_len=15)
    assert out.count("The SMF shall send X.") == 1
    assert "The AMF shall receive Y." in out


def test_normalize_table_cell_applies_list_dedupe() -> None:
    assert (
        normalize_table_cell_text("Note A; Note A; Note B")
        == "Note A; Note B"
    )


def test_clean_table_matrix_collapses_horizontal_and_vertical_merges(tmp_path: Path) -> None:
    path = tmp_path / "merged.docx"
    doc = Document()
    t = doc.add_table(rows=2, cols=4)
    t.cell(0, 0).text = "H0"
    t.cell(0, 1).text = "H1"
    t.cell(0, 2).text = "H2"
    t.cell(0, 3).text = "H3"
    t.cell(1, 0).text = "A"
    t.cell(1, 1).text = "B"
    t.cell(1, 2).text = "C"
    t.cell(1, 3).text = "D"
    t.cell(0, 0).merge(t.cell(0, 1))
    t.cell(1, 0).merge(t.cell(1, 2))
    doc.save(path)

    doc2 = Document(path)
    matrix = clean_table_matrix(doc2.tables[0])
    assert matrix[0][:3] == ["H0 H1", "H2", "H3"]
    assert matrix[1][:2] == ["A B C", "D"]

    path_v = tmp_path / "merged_v.docx"
    doc_v = Document()
    tv = doc_v.add_table(rows=3, cols=2)
    tv.cell(0, 0).text = "Name"
    tv.cell(0, 1).text = "Val"
    tv.cell(1, 0).text = "Span"
    tv.cell(1, 1).text = "x"
    tv.cell(2, 0).text = "y"
    tv.cell(2, 1).text = "z"
    tv.cell(1, 0).merge(tv.cell(2, 0))
    doc_v.save(path_v)
    matrix_v = clean_table_matrix(Document(path_v).tables[0])
    assert matrix_v[1] == ["Span y", "x"]
    assert matrix_v[2] == ["", "z"]
    linearized = table_to_linearized_text(matrix_v, "T")
    assert linearized.count("Span") == 1


def test_dedupe_duplicate_cell_texts_collapses_merged_and_interleaved_cells() -> None:
    label = "Odd/even indication (octet 4) Bit"
    assert dedupe_duplicate_cell_texts_preserve_order([label] * 10) == [label]
    assert dedupe_duplicate_cell_texts_preserve_order(["A", "A", "B", "B", "B"]) == ["A", "B"]
    assert dedupe_duplicate_cell_texts_preserve_order([label, "", label, "", label]) == [label]
    assert dedupe_duplicate_cell_texts_preserve_order(["A", "B", "A"]) == ["A", "B"]


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
    assert split_clause_heading("5.28a.3 Topology Information for TSN TN") == ("5.28a.3", "Topology Information for TSN TN")
    assert split_clause_heading("5G architecture") is None


def test_parser_keeps_mixed_alphanumeric_clause_ids(tmp_path: Path) -> None:
    source = tmp_path / "mixed-clause.docx"
    doc = Document()
    cover = doc.add_table(rows=3, cols=1)
    cover.cell(0, 0).text = "3GPP TS 23.501 V18.12.0 (2025-12)"
    cover.cell(1, 0).text = "Technical Specification"
    cover.cell(2, 0).text = "System architecture for the 5G System (5GS); Stage 2 (Release 18)"
    doc.add_paragraph("5.28a.3 Topology Information for TSN TN", style="Heading 3")
    doc.add_paragraph("Topology details.")
    doc.save(source)

    parser = DocxClauseParser()
    records = parser.parse(source, SpecMetadata(spec_no="23501"))

    clause_docs = [record for record in records if record.doc_type == "clause_doc"]
    assert [record.clause_id for record in clause_docs] == ["5.28a.3"]
    assert clause_docs[0].clause_title == "Topology Information for TSN TN"


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
