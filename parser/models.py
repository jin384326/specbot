from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class BaseDocRecord:
    doc_id: str
    doc_type: str
    content_kind: str
    spec_no: str = ""
    spec_title: str = ""
    release: str = ""
    release_data: str = ""
    series: str = ""
    ts_or_tr: str = ""
    stage_hint: str = ""
    clause_id: str = ""
    clause_title: str = ""
    clause_path: list[str] = field(default_factory=list)
    parent_clause_id: str = ""
    text: str = ""
    summary: str = ""
    retrieval_weight: float = 1.0
    keywords: list[str] = field(default_factory=list)
    anchor_terms: list[str] = field(default_factory=list)
    ie_names: list[str] = field(default_factory=list)
    message_names: list[str] = field(default_factory=list)
    procedure_names: list[str] = field(default_factory=list)
    table_headers: list[str] = field(default_factory=list)
    acronyms: list[str] = field(default_factory=list)
    camel_case_identifiers: list[str] = field(default_factory=list)
    referenced_specs: list[str] = field(default_factory=list)
    referenced_clauses: list[str] = field(default_factory=list)
    source_file: str = ""
    table_title: str = ""
    order_in_source: int = 0
    version_tag: str = ""
    domain_hint: list[str] = field(default_factory=list)
    embedding_text: str = ""
    embedding_model: str = ""
    embedding_dim: int = 0
    dense_vector: list[float] = field(default_factory=list)
    table_id: str = ""
    row_index: int = -1
    row_header: str = ""
    row_cells: list[str] = field(default_factory=list)
    table_raw: list[list[str]] = field(default_factory=list)
    table_markdown: str = ""
    passage_id: str = ""
    passage_index: int = -1
    paragraph_start_index: int = -1
    paragraph_end_index: int = -1
    entity_type: str = ""
    entity_name: str = ""
    source_doc_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ClauseDoc(BaseDocRecord):
    doc_type: str = "clause_doc"
    content_kind: str = "clause"


@dataclass
class PassageDoc(BaseDocRecord):
    doc_type: str = "passage_doc"
    content_kind: str = "passage"


@dataclass
class TableDoc(BaseDocRecord):
    doc_type: str = "table_doc"
    content_kind: str = "table"


@dataclass
class TableRowDoc(BaseDocRecord):
    doc_type: str = "table_row_doc"
    content_kind: str = "table_row"


@dataclass
class EntityDoc(BaseDocRecord):
    doc_type: str = "entity_doc"
    content_kind: str = "entity"


DocRecord = ClauseDoc | PassageDoc | TableDoc | TableRowDoc | EntityDoc


DOC_TYPE_TO_CLASS = {
    "clause_doc": ClauseDoc,
    "passage_doc": PassageDoc,
    "table_doc": TableDoc,
    "table_row_doc": TableRowDoc,
    "entity_doc": EntityDoc,
}


def doc_record_from_dict(data: dict[str, Any]) -> DocRecord:
    doc_type = data.get("doc_type", "clause_doc")
    cls = DOC_TYPE_TO_CLASS.get(doc_type, ClauseDoc)
    return cls(**data)
