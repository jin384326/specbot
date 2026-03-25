from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from app.clause_browser.backend.domain import ClauseRecord, ClauseSummary, ClauseTreeNode, DocumentSummary


class ClauseRepository:
    def __init__(self, corpus_path: str | Path) -> None:
        self._corpus_path = Path(corpus_path)
        if not self._corpus_path.is_file():
            raise FileNotFoundError(f"Clause corpus not found: {self._corpus_path}")

        self._records_by_spec: dict[str, dict[str, ClauseRecord]] = defaultdict(dict)
        self._children_by_spec: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
        self._document_summaries: list[DocumentSummary] = []
        self._descendant_counts: dict[tuple[str, str], int] = {}
        self._load()

    @property
    def corpus_path(self) -> Path:
        return self._corpus_path

    def list_documents(self, query: str = "", limit: int = 50) -> list[DocumentSummary]:
        normalized = query.strip().casefold()
        summaries = self._document_summaries
        if normalized:
            summaries = [
                item
                for item in summaries
                if normalized in item.spec_no.casefold()
                or normalized in item.spec_title.casefold()
                or normalized in item.source_file.casefold()
            ]
        return summaries[:limit]

    def get_document_summary(self, spec_no: str) -> DocumentSummary:
        for summary in self._document_summaries:
            if summary.spec_no == spec_no:
                return summary
        raise KeyError(f"Unknown document: {spec_no}")

    def has_clause(self, spec_no: str, clause_id: str) -> bool:
        records = self._records_by_spec.get(spec_no)
        if not records:
            return False
        return clause_id in records

    def list_clauses(self, spec_no: str, query: str = "", limit: int = 100, include_all: bool = False) -> list[ClauseSummary]:
        records = self._records_by_spec.get(spec_no)
        if not records:
            raise KeyError(f"Unknown document: {spec_no}")

        normalized = query.strip().casefold()
        candidates = sorted(records.values(), key=lambda item: item.order_in_source)
        if normalized:
            candidates = [
                item
                for item in candidates
                if normalized in item.clause_id.casefold()
                or normalized in item.clause_title.casefold()
                or normalized in item.text.casefold()
            ]
        elif not include_all:
            candidates = [item for item in candidates if not item.parent_clause_id or item.parent_clause_id not in records]

        return [
            ClauseSummary(
                key=item.key,
                spec_no=item.spec_no,
                clause_id=item.clause_id,
                clause_title=item.clause_title,
                clause_path=item.clause_path,
                parent_clause_id=item.parent_clause_id,
                child_count=len(self._children_by_spec[item.spec_no].get(item.clause_id, [])),
                descendant_count=self._descendant_counts[(item.spec_no, item.clause_id)],
                text_preview=self._preview(item.text),
            )
            for item in candidates[:limit]
        ]

    def get_subtree(self, spec_no: str, clause_id: str) -> ClauseTreeNode:
        records = self._records_by_spec.get(spec_no)
        if not records:
            raise KeyError(f"Unknown document: {spec_no}")
        if clause_id not in records:
            raise KeyError(f"Unknown clause: {spec_no}:{clause_id}")
        return self._build_tree(records[clause_id])

    def _synthesize_missing_ancestors(self, by_spec_order: dict[str, list[ClauseRecord]]) -> None:
        for spec_no, items in list(by_spec_order.items()):
            records = self._records_by_spec[spec_no]
            synthetic_records: list[ClauseRecord] = []
            for item in list(items):
                path_parts = list(item.clause_path)
                for index, ancestor_id in enumerate(path_parts[:-1]):
                    if ancestor_id in records:
                        continue
                    parent_clause_id = path_parts[index - 1] if index > 0 else ""
                    synthetic = ClauseRecord(
                        key=f"{spec_no}:{ancestor_id}",
                        spec_no=spec_no,
                        spec_title=item.spec_title,
                        clause_id=ancestor_id,
                        clause_title=ancestor_id,
                        text="",
                        parent_clause_id=parent_clause_id,
                        clause_path=tuple(path_parts[: index + 1]),
                        source_file=item.source_file,
                    order_in_source=max(0, item.order_in_source - (len(path_parts) - index)),
                    blocks=tuple(),
                    )
                    records[ancestor_id] = synthetic
                    synthetic_records.append(synthetic)
            if synthetic_records:
                by_spec_order[spec_no] = [*items, *synthetic_records]

    def _load(self) -> None:
        by_spec_order: dict[str, list[ClauseRecord]] = defaultdict(list)

        with self._corpus_path.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                payload = json.loads(raw_line)
                if payload.get("doc_type") != "clause_doc":
                    continue
                spec_no = str(payload.get("spec_no") or "").strip()
                clause_id = str(payload.get("clause_id") or "").strip()
                if not spec_no or not clause_id:
                    continue
                record = ClauseRecord(
                    key=f"{spec_no}:{clause_id}",
                    spec_no=spec_no,
                    spec_title=str(payload.get("spec_title") or "").strip(),
                    clause_id=clause_id,
                    clause_title=str(payload.get("clause_title") or "").strip() or clause_id,
                    text=str(payload.get("text") or "").strip(),
                    parent_clause_id=str(payload.get("parent_clause_id") or "").strip(),
                    clause_path=tuple(str(part) for part in payload.get("clause_path") or []),
                    source_file=str(payload.get("source_file") or "").strip(),
                    order_in_source=int(payload.get("order_in_source") or 0),
                    blocks=tuple(payload.get("blocks") or []),
                )
                self._records_by_spec[spec_no][clause_id] = record
                by_spec_order[spec_no].append(record)

        self._synthesize_missing_ancestors(by_spec_order)

        for spec_no, records in by_spec_order.items():
            ordered = sorted(records, key=lambda item: item.order_in_source)
            for record in ordered:
                if record.parent_clause_id and record.parent_clause_id in self._records_by_spec[spec_no]:
                    self._children_by_spec[spec_no][record.parent_clause_id].append(record.clause_id)
            for child_ids in self._children_by_spec[spec_no].values():
                child_ids.sort(key=lambda clause_id: self._records_by_spec[spec_no][clause_id].order_in_source)

            top_level_count = sum(
                1
                for record in ordered
                if not record.parent_clause_id or record.parent_clause_id not in self._records_by_spec[spec_no]
            )
            first = ordered[0]
            self._document_summaries.append(
                DocumentSummary(
                    spec_no=spec_no,
                    spec_title=first.spec_title,
                    source_file=first.source_file,
                    clause_count=len(ordered),
                    top_level_clause_count=top_level_count,
                )
            )

        self._document_summaries.sort(key=lambda item: item.spec_no)

        for spec_no, records in self._records_by_spec.items():
            for clause_id in records:
                self._descendant_counts[(spec_no, clause_id)] = self._count_descendants(spec_no, clause_id)

    def _count_descendants(self, spec_no: str, clause_id: str) -> int:
        total = 0
        for child_id in self._children_by_spec[spec_no].get(clause_id, []):
            total += 1 + self._count_descendants(spec_no, child_id)
        return total

    def _build_tree(self, record: ClauseRecord) -> ClauseTreeNode:
        child_ids = self._children_by_spec[record.spec_no].get(record.clause_id, [])
        children = tuple(self._build_tree(self._records_by_spec[record.spec_no][child_id]) for child_id in child_ids)
        return ClauseTreeNode(
            key=record.key,
            spec_no=record.spec_no,
            spec_title=record.spec_title,
            clause_id=record.clause_id,
            clause_title=record.clause_title,
            text=record.text,
            parent_clause_id=record.parent_clause_id,
            clause_path=record.clause_path,
            source_file=record.source_file,
            order_in_source=record.order_in_source,
            child_count=len(child_ids),
            descendant_count=self._descendant_counts[(record.spec_no, record.clause_id)],
            blocks=record.blocks,
            children=children,
        )

    @staticmethod
    def _preview(text: str, max_chars: int = 180) -> str:
        normalized = " ".join((text or "").split())
        if len(normalized) <= max_chars:
            return normalized
        return normalized[: max_chars - 1].rstrip() + "..."
