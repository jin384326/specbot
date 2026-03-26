from __future__ import annotations

import asyncio
import json
import base64
from pathlib import Path

from docx import Document
from docx.enum.style import WD_STYLE_TYPE
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt
from fastapi import HTTPException
from fastapi.routing import APIRoute

from app.clause_browser.api import ExportRequest, LLMActionRequest, SpecbotQueryRequest
from app.clause_browser.preprocess import build_clause_browser_corpus
from app.clause_browser.server import ClauseBrowserSettings, create_app
from app.clause_browser.services import (
    DocxExportService,
    LLMActionService,
    SpecbotQueryDefaults,
    SpecbotQueryService,
    sanitize_file_stem,
)
from app.specbot_query_server import PersistentSpecbotQueryEngine


def write_corpus(path: Path) -> None:
    records = [
        {
            "doc_type": "clause_doc",
            "spec_no": "23501",
            "spec_title": "System architecture",
            "clause_id": "5",
            "clause_title": "Session management",
            "parent_clause_id": "",
            "clause_path": ["5"],
            "text": "Session management overview.",
            "source_file": str(path.parent / "23501.docx"),
            "order_in_source": 1,
        },
        {
            "doc_type": "clause_doc",
            "spec_no": "23501",
            "spec_title": "System architecture",
            "clause_id": "5.1",
            "clause_title": "PDU session procedures",
            "parent_clause_id": "5",
            "clause_path": ["5", "5.1"],
            "text": "Detailed clause body.",
            "source_file": str(path.parent / "23501.docx"),
            "order_in_source": 2,
        },
        {
            "doc_type": "clause_doc",
            "spec_no": "23501",
            "spec_title": "System architecture",
            "clause_id": "5.1.1",
            "clause_title": "Request handling",
            "parent_clause_id": "5.1",
            "clause_path": ["5", "5.1", "5.1.1"],
            "text": "Request handling details.",
            "source_file": str(path.parent / "23501.docx"),
            "order_in_source": 3,
        },
        {
            "doc_type": "clause_doc",
            "spec_no": "24501",
            "spec_title": "Core network procedures",
            "clause_id": "1",
            "clause_title": "Scope",
            "parent_clause_id": "",
            "clause_path": ["1"],
            "text": "Another document.",
            "source_file": str(path.parent / "24501.docx"),
            "order_in_source": 1,
        },
        {
            "doc_type": "clause_doc",
            "spec_no": "23502",
            "spec_title": "Procedures for the 5G System (5GS); Stage 2 (Release 18)",
            "clause_id": "4.2.2.2",
            "clause_title": "PDU session establishment",
            "parent_clause_id": "",
            "clause_path": ["4.2.2.2"],
            "text": "",
            "source_file": str(path.parent / "23502.docx"),
            "order_in_source": 1,
            "blocks": [
                {
                    "type": "table",
                    "rows": [
                        ["Field", "Description"],
                        ["redundantPduSessionInfo", "Contains RSN and PDU Session Pair ID"],
                    ],
                }
            ],
        },
    ]
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record) + "\n")


def write_docx_files(tmp_path: Path) -> None:
    image_path = tmp_path / "tiny.png"
    image_path.write_bytes(
        base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a7VQAAAAASUVORK5CYII="
        )
    )

    doc = Document()
    doc.add_paragraph("5 Session management", style="Heading 1")
    doc.add_paragraph("Session management overview.")
    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "Name"
    table.cell(0, 1).text = "Value"
    table.cell(1, 0).text = "Mode"
    table.cell(1, 1).text = "SSC1"
    doc.add_paragraph().add_run().add_picture(str(image_path))
    doc.add_paragraph("5.1 PDU session procedures", style="Heading 2")
    doc.add_paragraph("Detailed clause body.")
    doc.add_paragraph("5.1.1 Request handling", style="Heading 3")
    doc.add_paragraph("Request handling details.")
    doc.save(tmp_path / "23501.docx")

    doc2 = Document()
    doc2.add_paragraph("1 Scope", style="Heading 1")
    doc2.add_paragraph("Another document.")
    doc2.save(tmp_path / "24501.docx")


def write_docx_with_body_numbered_paragraph(tmp_path: Path) -> Path:
    doc = Document()
    doc.styles.add_style("B1", WD_STYLE_TYPE.PARAGRAPH)
    doc.add_paragraph("5 Session management", style="Heading 1")
    doc.add_paragraph("Overview text.")
    doc.add_paragraph("3 Packet Delay Budget (including Core Network Packet Delay Budget);", style="B1")
    doc.add_paragraph("This line must stay in clause 5.")
    path = tmp_path / "numbered-body.docx"
    doc.save(path)
    return path


def write_docx_with_outline_level_heading(tmp_path: Path) -> Path:
    doc = Document()
    doc.add_paragraph("8.2.22 Offending IE", style="Heading 2")
    doc.add_paragraph("Offending IE body.")
    paragraph = doc.add_paragraph("8.2.222 N6 Jitter Measurement")
    p_pr = paragraph._p.get_or_add_pPr()
    outline = OxmlElement("w:outlineLvl")
    outline.set(qn("w:val"), "2")
    p_pr.append(outline)
    doc.add_paragraph("The N6 Jitter Measurement IE contains a N6 jitter measurement.")
    path = tmp_path / "outline-level-heading.docx"
    doc.save(path)
    return path


def write_docx_with_merged_table(tmp_path: Path) -> Path:
    doc = Document()
    doc.add_paragraph("5 Session management", style="Heading 1")
    table = doc.add_table(rows=3, cols=3)
    table.cell(0, 0).text = "Group"
    table.cell(0, 1).text = "Field"
    table.cell(0, 2).text = "Value"
    table.cell(1, 0).text = "Session"
    table.cell(1, 1).text = "Mode"
    table.cell(1, 2).text = "SSC1"
    table.cell(2, 0).text = "Will be merged away"
    table.cell(2, 1).text = "Timer"
    table.cell(2, 2).text = "30s"
    table.cell(1, 0).merge(table.cell(2, 0))
    path = tmp_path / "23501.docx"
    doc.save(path)
    return path


def write_docx_with_indented_paragraph(tmp_path: Path) -> Path:
    doc = Document()
    doc.add_paragraph("5 Session management", style="Heading 1")
    paragraph = doc.add_paragraph(
        "1a. (UE initiated modification) The UE initiates the PDU Session Modification procedure."
    )
    paragraph.paragraph_format.left_indent = Pt(18)
    paragraph.paragraph_format.first_line_indent = Pt(-18)
    path = tmp_path / "23501-indented-paragraph.docx"
    doc.save(path)
    return path


def build_app(tmp_path: Path):
    write_docx_files(tmp_path)
    export_dir = tmp_path / "exports"
    browser_corpus_path = tmp_path / "browser-corpus.jsonl"
    build_clause_browser_corpus(
        inputs=[str(tmp_path / "23501.docx"), str(tmp_path / "24501.docx")],
        output_path=browser_corpus_path,
        media_dir=tmp_path / "media",
    )
    with browser_corpus_path.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "doc_type": "clause_doc",
                    "content_kind": "clause",
                    "doc_id": "23502:clause:4.2.2.2",
                    "spec_no": "23502",
                    "spec_title": "Procedures for the 5G System (5GS); Stage 2 (Release 18)",
                    "clause_id": "4.2.2.2",
                    "clause_title": "PDU session establishment",
                    "parent_clause_id": "",
                    "clause_path": ["4.2.2.2"],
                    "text": "",
                    "source_file": str(tmp_path / "23502.docx"),
                    "order_in_source": 1,
                    "blocks": [
                        {
                            "type": "table",
                            "rows": [
                                ["Field", "Description"],
                                ["redundantPduSessionInfo", "Contains RSN and PDU Session Pair ID"],
                            ],
                        }
                    ],
                }
            )
            + "\n"
        )
    return create_app(
        ClauseBrowserSettings(
            project_root=tmp_path,
            corpus_path=browser_corpus_path,
            export_dir=export_dir,
            media_dir=tmp_path / "media",
            cors_origins=(),
            llm_provider="mock",
            llm_model="mock-model",
            languages=(("ko", "Korean"), ("en", "English")),
            specbot_query_api_url="http://127.0.0.1:8010",
        )
    )


def get_endpoint(app, path: str):
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path == path:
            return route.endpoint
    raise AssertionError(f"Route not found: {path}")


def test_documents_endpoint_lists_specs(tmp_path: Path) -> None:
    app = build_app(tmp_path)
    endpoint = get_endpoint(app, "/api/clause-browser/documents")

    payload = endpoint()
    assert payload["success"] is True
    assert [item["specNo"] for item in payload["data"]["items"]] == ["23501", "23502", "24501"]


def test_translation_split_preserves_paragraph_boundaries() -> None:
    first = "A" * 7000
    second = "B" * 6990
    text = f"{first}\n\n{second}"

    chunks = LLMActionService._split_translation_text(text, limit=12000)

    assert len(chunks) == 2
    assert chunks[0] == first
    assert chunks[1] == second


def test_documents_endpoint_can_filter_by_clause_and_body_text_before_document_selection(tmp_path: Path) -> None:
    app = build_app(tmp_path)
    endpoint = get_endpoint(app, "/api/clause-browser/documents")

    by_clause_title = endpoint("", "request handling")["data"]["items"]
    assert [item["specNo"] for item in by_clause_title] == ["23501"]

    by_body_text = endpoint("", "another document")["data"]["items"]
    assert [item["specNo"] for item in by_body_text] == ["24501"]

    by_table_text = endpoint("", "RSN")["data"]["items"]
    assert [item["specNo"] for item in by_table_text] == ["23502"]


def test_clause_list_search_matches_clause_body_text(tmp_path: Path) -> None:
    app = build_app(tmp_path)
    endpoint = get_endpoint(app, "/api/clause-browser/documents/{spec_no}/clauses")

    payload = endpoint("23501", "request handling details", 100)["data"]["items"]
    assert [item["clauseId"] for item in payload] == ["5.1.1"]


def test_clause_list_search_matches_table_block_text(tmp_path: Path) -> None:
    app = build_app(tmp_path)
    endpoint = get_endpoint(app, "/api/clause-browser/documents/{spec_no}/clauses")

    payload = endpoint("23502", "RSN", 100)["data"]["items"]
    assert [item["clauseId"] for item in payload] == ["4.2.2.2"]
    assert "rsn" in payload[0]["searchText"]


def test_synthesized_ancestor_clause_is_searchable(tmp_path: Path) -> None:
    export_dir = tmp_path / "exports"
    write_docx_files(tmp_path)
    browser_corpus_path = tmp_path / "browser-corpus.jsonl"
    build_clause_browser_corpus(
        inputs=[str(tmp_path / "23501.docx")],
        output_path=browser_corpus_path,
        media_dir=tmp_path / "media",
    )
    with browser_corpus_path.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "doc_type": "clause_doc",
                    "content_kind": "clause",
                    "doc_id": "29512:clause:5.5.2.1",
                    "spec_no": "29512",
                    "spec_title": "Example spec",
                    "clause_id": "5.5.2.1",
                    "clause_title": "Description",
                    "parent_clause_id": "5.5.2",
                    "clause_path": ["5", "5.5", "5.5.2", "5.5.2.1"],
                    "text": "Leaf body",
                    "source_file": str(tmp_path / "23501.docx"),
                    "order_in_source": 10,
                    "blocks": [{"type": "paragraph", "text": "Leaf body"}],
                }
            )
            + "\n"
        )
    app = create_app(
        ClauseBrowserSettings(
            project_root=tmp_path,
            corpus_path=browser_corpus_path,
            export_dir=export_dir,
            media_dir=tmp_path / "media",
            cors_origins=(),
            llm_provider="mock",
            llm_model="mock-model",
            languages=(("ko", "Korean"), ("en", "English")),
            specbot_query_api_url="http://127.0.0.1:8010",
        )
    )
    endpoint = get_endpoint(app, "/api/clause-browser/documents/{spec_no}/clauses")
    payload = endpoint("29512", "5.5.2", 100)["data"]["items"]
    assert any(item["clauseId"] == "5.5.2" for item in payload)


def test_subtree_endpoint_returns_descendants(tmp_path: Path) -> None:
    app = build_app(tmp_path)
    endpoint = get_endpoint(app, "/api/clause-browser/documents/{spec_no}/clauses/{clause_id:path}/subtree")

    payload = endpoint("23501", "5")["data"]
    assert payload["clauseId"] == "5"
    assert [block["type"] for block in payload["blocks"]] == ["paragraph", "table", "image"]
    assert payload["children"][0]["clauseId"] == "5.1"
    assert payload["children"][0]["children"][0]["clauseId"] == "5.1.1"
    assert payload["blocks"][1]["rows"][1][1] == "SSC1"


def test_numbered_body_paragraph_does_not_become_clause(tmp_path: Path) -> None:
    source_path = write_docx_with_body_numbered_paragraph(tmp_path)
    browser_corpus_path = tmp_path / "browser-corpus.jsonl"

    build_clause_browser_corpus(
        inputs=[str(source_path)],
        output_path=browser_corpus_path,
        media_dir=tmp_path / "media",
    )

    records = [json.loads(line) for line in browser_corpus_path.open(encoding="utf-8")]
    clause_ids = [record["clause_id"] for record in records]
    assert clause_ids == ["5"]
    assert "Packet Delay Budget" not in records[0]["clause_title"]
    assert "3 Packet Delay Budget (including Core Network Packet Delay Budget);" in records[0]["text"]


def test_missing_clause_returns_404(tmp_path: Path) -> None:
    app = build_app(tmp_path)
    endpoint = get_endpoint(app, "/api/clause-browser/documents/{spec_no}/clauses/{clause_id:path}/subtree")

    try:
        endpoint("23501", "9.9")
    except HTTPException as exc:
        assert exc.status_code == 404
    else:
        raise AssertionError("Expected HTTPException")


def test_outline_level_heading_becomes_clause(tmp_path: Path) -> None:
    source_path = write_docx_with_outline_level_heading(tmp_path)
    browser_corpus_path = tmp_path / "browser-corpus.jsonl"

    build_clause_browser_corpus(
        inputs=[str(source_path)],
        output_path=browser_corpus_path,
        media_dir=tmp_path / "media",
    )

    records = [json.loads(line) for line in browser_corpus_path.open(encoding="utf-8")]
    clause_ids = [record["clause_id"] for record in records]
    assert "8.2.22" in clause_ids
    assert "8.2.222" in clause_ids
    outline_record = next(record for record in records if record["clause_id"] == "8.2.222")
    assert outline_record["clause_title"] == "N6 Jitter Measurement"


def test_subtree_endpoint_preserves_table_rowspan_metadata(tmp_path: Path) -> None:
    source_path = write_docx_with_merged_table(tmp_path)
    browser_corpus_path = tmp_path / "browser-corpus.jsonl"
    with browser_corpus_path.open("w", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "doc_type": "clause_doc",
                    "content_kind": "clause",
                    "doc_id": "23501:clause:5",
                    "spec_no": "23501",
                    "spec_title": "Merged table spec",
                    "clause_id": "5",
                    "clause_title": "Session management",
                    "parent_clause_id": "",
                    "clause_path": ["5"],
                    "text": "",
                    "source_file": str(source_path),
                    "order_in_source": 1,
                    "blocks": [],
                }
            )
            + "\n"
        )
    app = create_app(
        ClauseBrowserSettings(
            project_root=tmp_path,
            corpus_path=browser_corpus_path,
            export_dir=tmp_path / "exports",
            media_dir=tmp_path / "media",
            cors_origins=(),
            llm_provider="mock",
            llm_model="mock-model",
            languages=(("ko", "Korean"), ("en", "English")),
            specbot_query_api_url="http://127.0.0.1:8010",
        )
    )
    endpoint = get_endpoint(app, "/api/clause-browser/documents/{spec_no}/clauses/{clause_id:path}/subtree")
    payload = endpoint("23501", "5")["data"]
    table_block = next(block for block in payload["blocks"] if block["type"] == "table")
    assert "cells" in table_block
    assert table_block["cells"][1][0]["text"] == "Session Will be merged away"
    assert table_block["cells"][1][0]["rowspan"] == 2
    assert table_block["cells"][1][0]["colspan"] == 1


def test_subtree_endpoint_returns_paragraph_indent_metadata(tmp_path: Path) -> None:
    source_path = write_docx_with_indented_paragraph(tmp_path)
    browser_corpus_path = tmp_path / "browser-corpus.jsonl"

    build_clause_browser_corpus(
        inputs=[str(source_path)],
        output_path=browser_corpus_path,
        media_dir=tmp_path / "media",
    )

    app = create_app(
        ClauseBrowserSettings(
            project_root=tmp_path,
            corpus_path=browser_corpus_path,
            export_dir=tmp_path / "exports",
            media_dir=tmp_path / "media",
            cors_origins=(),
            llm_provider="mock",
            llm_model="mock-model",
            languages=(("ko", "Korean"), ("en", "English")),
            specbot_query_api_url="http://127.0.0.1:8010",
        )
    )
    endpoint = get_endpoint(app, "/api/clause-browser/documents/{spec_no}/clauses/{clause_id:path}/subtree")

    payload = endpoint("23501", "5")["data"]
    paragraph_block = next(block for block in payload["blocks"] if block["type"] == "paragraph")

    assert paragraph_block["format"]["leftIndentPx"] == 24
    assert paragraph_block["format"]["textIndentPx"] == -24


def test_docx_export_endpoint_saves_file(tmp_path: Path) -> None:
    app = build_app(tmp_path)
    subtree_endpoint = get_endpoint(app, "/api/clause-browser/documents/{spec_no}/clauses/{clause_id:path}/subtree")
    export_endpoint = get_endpoint(app, "/api/clause-browser/exports/docx")
    subtree = subtree_endpoint("23501", "5")["data"]

    payload = export_endpoint(ExportRequest(title="Session Export", roots=[subtree]))["data"]
    exported_path = tmp_path / payload["relativePath"]
    assert exported_path.is_file()
    exported = Document(exported_path)
    headings = [p.text for p in exported.paragraphs if p.style.name.startswith("Heading")]
    assert "5 Session management" in headings
    assert "5.1 PDU session procedures" in headings


def test_llm_action_endpoint_returns_mock_translation(tmp_path: Path) -> None:
    app = build_app(tmp_path)
    endpoint = get_endpoint(app, "/api/clause-browser/llm-actions")

    payload = endpoint(
        LLMActionRequest(
            actionType="translate",
            text="Session management",
            sourceLanguage="en",
            targetLanguage="ko",
            context="23501 / 5",
        )
    )["data"]
    assert payload["provider"] == "mock"
    assert payload["outputText"] == "[en->ko] Session management"


def test_llm_action_rejects_empty_text(tmp_path: Path) -> None:
    app = build_app(tmp_path)
    endpoint = get_endpoint(app, "/api/clause-browser/llm-actions")

    try:
        endpoint(
            LLMActionRequest(
                actionType="translate",
                text=" ",
                sourceLanguage="en",
                targetLanguage="ko",
            )
        )
    except HTTPException as exc:
        assert exc.status_code == 400
        assert "Select text" in exc.detail
    else:
        raise AssertionError("Expected HTTPException")


def test_specbot_query_endpoint_returns_hits(tmp_path: Path) -> None:
    class FakeSpecbotQueryService(SpecbotQueryService):
        def __init__(self, project_root: Path) -> None:
            super().__init__(project_root=project_root, defaults=SpecbotQueryDefaults())
            self.last_exclude_specs = None
            self.last_exclude_clauses = None

        def run(
            self,
            query: str,
            settings: dict[str, object] | None = None,
            exclude_specs: list[str] | None = None,
            exclude_clauses: list[dict[str, object]] | None = None,
        ) -> dict[str, object]:
            self.last_exclude_specs = exclude_specs
            self.last_exclude_clauses = exclude_clauses
            return {
                "query": query,
                "settings": settings or self.defaults.to_dict(),
                "hits": [
                    {
                        "specNo": "23501",
                        "clauseId": "5.1",
                        "parentClauseId": "5",
                        "clausePath": ["5", "5.1"],
                        "textPreview": "Detailed clause body.",
                    }
                ],
                "rawResult": {"relevant_documents": []},
                "command": "python3 -m app.main iterative-query-vespa-http ...",
            }

    fake_service = FakeSpecbotQueryService(tmp_path)
    app = build_app(tmp_path)
    app = create_app(
        ClauseBrowserSettings(
            project_root=tmp_path,
            corpus_path=tmp_path / "browser-corpus.jsonl",
            export_dir=tmp_path / "exports",
            media_dir=tmp_path / "media",
            cors_origins=(),
            llm_provider="mock",
            llm_model="mock-model",
            languages=(("ko", "Korean"), ("en", "English")),
            specbot_query_api_url="http://127.0.0.1:8010",
        ),
        specbot_service=fake_service,
    )
    endpoint = get_endpoint(app, "/api/clause-browser/specbot/query")

    payload = asyncio.run(
        endpoint(
            None,
            SpecbotQueryRequest(
                query="End to End Redundant Paths",
                excludeSpecs=["23502"],
                excludeClauses=[{"specNo": "23501", "clauseId": "5.2"}],
            ),
        )
    )["data"]
    assert payload["query"] == "End to End Redundant Paths"
    assert payload["hits"][0]["specNo"] == "23501"
    assert fake_service.last_exclude_specs == ["23502"]
    assert fake_service.last_exclude_clauses == [{"specNo": "23501", "clauseId": "5.2"}]


def test_specbot_query_exclusion_is_exact_spec_clause_pair() -> None:
    hits = [
        {"specNo": "23502", "clauseId": "4.2.2.2"},
        {"specNo": "29512", "clauseId": "4.2.2.2"},
        {"specNo": "23502", "clauseId": "4.2.2.3"},
    ]
    filtered = PersistentSpecbotQueryEngine._apply_exclusions(
        hits,
        exclude_specs=[],
        exclude_clauses=[{"specNo": "23502", "clauseId": "4.2.2.2"}],
    )
    assert filtered == [
        {"specNo": "29512", "clauseId": "4.2.2.2"},
        {"specNo": "23502", "clauseId": "4.2.2.3"},
    ]


def test_docx_export_service_adds_numeric_suffix(tmp_path: Path) -> None:
    export_dir = tmp_path / "exports"
    service = DocxExportService(export_dir=export_dir, project_root=tmp_path)
    roots = [
        {
            "clauseId": "5",
            "clauseTitle": "Session management",
            "text": "Body",
            "children": [],
        }
    ]

    first = service.export("My Export", roots)
    second = service.export("My Export", roots)

    assert first.file_name == "My-Export.docx"
    assert second.file_name == "My-Export-2.docx"


def test_sanitize_file_stem_removes_invalid_characters() -> None:
    assert sanitize_file_stem('A/B:C*D? E') == "ABCD-E"
