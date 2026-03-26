from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ClauseRecord:
    key: str
    spec_no: str
    spec_title: str
    clause_id: str
    clause_title: str
    text: str
    parent_clause_id: str
    clause_path: tuple[str, ...]
    source_file: str
    order_in_source: int
    blocks: tuple[dict[str, object], ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ClauseTreeNode:
    key: str
    spec_no: str
    spec_title: str
    clause_id: str
    clause_title: str
    text: str
    parent_clause_id: str
    clause_path: tuple[str, ...]
    source_file: str
    order_in_source: int
    child_count: int = 0
    descendant_count: int = 0
    blocks: tuple[dict[str, object], ...] = field(default_factory=tuple)
    children: tuple["ClauseTreeNode", ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "specNo": self.spec_no,
            "specTitle": self.spec_title,
            "clauseId": self.clause_id,
            "clauseTitle": self.clause_title,
            "text": self.text,
            "parentClauseId": self.parent_clause_id,
            "clausePath": list(self.clause_path),
            "sourceFile": self.source_file,
            "orderInSource": self.order_in_source,
            "childCount": self.child_count,
            "descendantCount": self.descendant_count,
            "blocks": [dict(block) for block in self.blocks],
            "children": [child.to_dict() for child in self.children],
        }


@dataclass(frozen=True)
class DocumentSummary:
    spec_no: str
    spec_title: str
    source_file: str
    clause_count: int
    top_level_clause_count: int

    def to_dict(self) -> dict[str, object]:
        return {
            "specNo": self.spec_no,
            "specTitle": self.spec_title,
            "sourceFile": self.source_file,
            "clauseCount": self.clause_count,
            "topLevelClauseCount": self.top_level_clause_count,
        }


@dataclass(frozen=True)
class ClauseSummary:
    key: str
    spec_no: str
    clause_id: str
    clause_title: str
    clause_path: tuple[str, ...]
    parent_clause_id: str
    child_count: int
    descendant_count: int
    text_preview: str
    search_text: str

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "specNo": self.spec_no,
            "clauseId": self.clause_id,
            "clauseTitle": self.clause_title,
            "clausePath": list(self.clause_path),
            "parentClauseId": self.parent_clause_id,
            "childCount": self.child_count,
            "descendantCount": self.descendant_count,
            "textPreview": self.text_preview,
            "searchText": self.search_text,
        }
