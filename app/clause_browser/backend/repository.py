from __future__ import annotations

import concurrent.futures
import json
import logging
import threading
import time
from collections import defaultdict
from pathlib import Path

from app.clause_browser.backend.domain import ClauseRecord, ClauseSummary, ClauseTreeNode, DocumentSummary

logger = logging.getLogger(__name__)


def _parse_clause_record_chunk(lines: list[str]) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for raw_line in lines:
        payload = json.loads(raw_line)
        if payload.get("doc_type") != "clause_doc":
            continue
        spec_no = str(payload.get("spec_no") or "").strip()
        clause_id = str(payload.get("clause_id") or "").strip()
        if not spec_no or not clause_id:
            continue
        items.append(payload)
    return items


class ClauseRepository:
    def __init__(self, corpus_path: str | Path, load_workers: int = 4) -> None:
        self._corpus_path = Path(corpus_path)
        if not self._corpus_path.is_file():
            raise FileNotFoundError(f"Clause corpus not found: {self._corpus_path}")
        self._load_workers = max(1, int(load_workers))

        self._records_by_document: dict[tuple[str, str, str], dict[str, ClauseRecord]] = defaultdict(dict)
        self._children_by_document: dict[tuple[str, str, str], dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
        self._document_summaries: list[DocumentSummary] = []
        self._descendant_counts: dict[tuple[str, str], int] = {}
        self._load()

    @property
    def corpus_path(self) -> Path:
        return self._corpus_path

    def list_release_scopes(self) -> list[dict[str, str]]:
        scopes = {
            (item.release_data, item.release)
            for item in self._document_summaries
            if item.release_data and item.release
        }
        return [
            {"releaseData": release_data, "release": release}
            for release_data, release in sorted(scopes)
        ]

    def list_documents(
        self,
        query: str = "",
        clause_query: str = "",
        limit: int = 50,
        release_data: str = "",
        release: str = "",
    ) -> list[DocumentSummary]:
        normalized = query.strip().casefold()
        normalized_clause = clause_query.strip().casefold()
        normalized_release_data = release_data.strip()
        normalized_release = release.strip()
        summaries = self._document_summaries
        if normalized_release_data:
            summaries = [item for item in summaries if item.release_data == normalized_release_data]
        if normalized_release:
            summaries = [item for item in summaries if item.release == normalized_release]
        if normalized:
            summaries = [
                item
                for item in summaries
                if normalized in item.spec_no.casefold()
                or normalized in item.spec_title.casefold()
                or normalized in item.source_file.casefold()
            ]
        if normalized_clause:
            summaries = [
                item
                for item in summaries
                if self._document_summary_matches_clause_query(item, normalized_clause)
            ]
        return summaries[:limit]

    def get_document_summary(self, spec_no: str) -> DocumentSummary:
        matches = [summary for summary in self._document_summaries if summary.spec_no == spec_no]
        if len(matches) == 1:
            return matches[0]
        if matches:
            return sorted(matches, key=lambda item: (item.release_data, item.release))[0]
        raise KeyError(f"Unknown document: {spec_no}")

    def has_clause(self, spec_no: str, clause_id: str, release_data: str = "", release: str = "") -> bool:
        records = self._get_records_for_document(spec_no, release_data, release)
        if not records:
            return False
        return clause_id in records

    def list_clauses(
        self,
        spec_no: str,
        query: str = "",
        limit: int = 100,
        include_all: bool = False,
        release_data: str = "",
        release: str = "",
    ) -> list[ClauseSummary]:
        records = self._get_records_for_document(spec_no, release_data, release)
        if not records:
            raise KeyError(f"Unknown document: {spec_no}")

        normalized = query.strip().casefold()
        candidates = sorted(records.values(), key=lambda item: item.order_in_source)
        if normalized:
            candidates = [
                item
                for item in candidates
                if normalized in self._record_search_text(item)
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
                child_count=len(self._children_by_document[self._document_key(item.spec_no, item.release_data, item.release)].get(item.clause_id, [])),
                descendant_count=self._descendant_counts[(item.key, item.clause_id)],
                text_preview=self._preview(item.text),
                search_text=self._record_search_text(item),
            )
            for item in candidates[:limit]
        ]

    def get_subtree(self, spec_no: str, clause_id: str, release_data: str = "", release: str = "") -> ClauseTreeNode:
        records = self._get_records_for_document(spec_no, release_data, release)
        if not records:
            raise KeyError(f"Unknown document: {spec_no}")
        if clause_id not in records:
            raise KeyError(f"Unknown clause: {spec_no}:{clause_id}")
        return self._build_tree(records[clause_id])

    def _synthesize_missing_ancestors(self, by_document_order: dict[tuple[str, str, str], list[ClauseRecord]]) -> None:
        for document_key, items in list(by_document_order.items()):
            spec_no = document_key[2]
            records = self._records_by_document[document_key]
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
                    release=item.release,
                    release_data=item.release_data,
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
                by_document_order[document_key] = [*items, *synthetic_records]

    def _load(self) -> None:
        by_document_order: dict[tuple[str, str, str], list[ClauseRecord]] = defaultdict(list)
        started_at = time.monotonic()
        logger.info(
            "Loading clause corpus path=%s workers=%d",
            self._corpus_path,
            self._load_workers,
        )
        chunks: list[list[str]] = []
        chunk: list[str] = []
        with self._corpus_path.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                chunk.append(raw_line)
                if len(chunk) >= 2000:
                    chunks.append(chunk)
                    chunk = []
            if chunk:
                chunks.append(chunk)
        logger.info(
            "Clause corpus split into %d chunks for parallel parsing path=%s",
            len(chunks),
            self._corpus_path,
        )

        payloads: list[dict[str, object]] = []
        if self._load_workers == 1 or len(chunks) <= 1:
            for chunk_index, chunk_lines in enumerate(chunks, start=1):
                payloads.extend(_parse_clause_record_chunk(chunk_lines))
                if chunk_index == 1 or chunk_index == len(chunks) or chunk_index % 10 == 0:
                    logger.info(
                        "Parsed clause corpus chunk %d/%d path=%s",
                        chunk_index,
                        len(chunks),
                        self._corpus_path,
                    )
        else:
            with concurrent.futures.ThreadPoolExecutor(max_workers=self._load_workers) as executor:
                futures = [
                    executor.submit(_parse_clause_record_chunk, chunk_lines)
                    for chunk_lines in chunks
                ]
                for chunk_index, future in enumerate(concurrent.futures.as_completed(futures), start=1):
                    payloads.extend(future.result())
                    if chunk_index == 1 or chunk_index == len(futures) or chunk_index % 10 == 0:
                        logger.info(
                            "Parsed clause corpus chunk %d/%d path=%s",
                            chunk_index,
                            len(futures),
                            self._corpus_path,
                        )
        logger.info(
            "Finished parsing clause corpus payloads path=%s payloads=%d elapsed=%.2fs",
            self._corpus_path,
            len(payloads),
            time.monotonic() - started_at,
        )

        for payload in payloads:
            spec_no = str(payload.get("spec_no") or "").strip()
            clause_id = str(payload.get("clause_id") or "").strip()
            record = ClauseRecord(
                key=f"{spec_no}:{clause_id}",
                spec_no=spec_no,
                spec_title=str(payload.get("spec_title") or "").strip(),
                release=str(payload.get("release") or "").strip(),
                release_data=str(payload.get("release_data") or "").strip(),
                clause_id=clause_id,
                clause_title=str(payload.get("clause_title") or "").strip() or clause_id,
                text=str(payload.get("text") or "").strip(),
                parent_clause_id=str(payload.get("parent_clause_id") or "").strip(),
                clause_path=tuple(str(part) for part in payload.get("clause_path") or []),
                source_file=str(payload.get("source_file") or "").strip(),
                order_in_source=int(payload.get("order_in_source") or 0),
                blocks=tuple(payload.get("blocks") or []),
            )
            document_key = self._document_key(spec_no, record.release_data, record.release)
            self._records_by_document[document_key][clause_id] = record
            by_document_order[document_key].append(record)
        logger.info(
            "Materialized clause records path=%s specs=%d clauses=%d elapsed=%.2fs",
            self._corpus_path,
            len(self._records_by_document),
            sum(len(items) for items in self._records_by_document.values()),
            time.monotonic() - started_at,
        )

        self._synthesize_missing_ancestors(by_document_order)
        logger.info(
            "Synthesized missing ancestors path=%s specs=%d clauses=%d elapsed=%.2fs",
            self._corpus_path,
            len(self._records_by_document),
            sum(len(items) for items in self._records_by_document.values()),
            time.monotonic() - started_at,
        )

        for document_key, records in by_document_order.items():
            spec_no = document_key[2]
            ordered = sorted(records, key=lambda item: item.order_in_source)
            for record in ordered:
                if record.parent_clause_id and record.parent_clause_id in self._records_by_document[document_key]:
                    self._children_by_document[document_key][record.parent_clause_id].append(record.clause_id)
            for child_ids in self._children_by_document[document_key].values():
                child_ids.sort(key=lambda clause_id: self._records_by_document[document_key][clause_id].order_in_source)

            top_level_count = sum(
                1
                for record in ordered
                if not record.parent_clause_id or record.parent_clause_id not in self._records_by_document[document_key]
            )
            first = ordered[0]
            self._document_summaries.append(
                DocumentSummary(
                    spec_no=spec_no,
                    spec_title=first.spec_title,
                    source_file=first.source_file,
                    release=first.release,
                    release_data=first.release_data,
                    clause_count=len(ordered),
                    top_level_clause_count=top_level_count,
                )
            )
        logger.info(
            "Built document summaries and child indexes path=%s documents=%d elapsed=%.2fs",
            self._corpus_path,
            len(self._document_summaries),
            time.monotonic() - started_at,
        )

        self._document_summaries.sort(key=lambda item: item.spec_no)
        logger.info(
            "Computing descendant counts path=%s clauses=%d elapsed=%.2fs",
            self._corpus_path,
            sum(len(items) for items in self._records_by_document.values()),
            time.monotonic() - started_at,
        )
        for document_key, records in self._records_by_document.items():
            self._compute_descendant_counts(document_key, records)
        logger.info(
            "Computed descendant counts path=%s entries=%d elapsed=%.2fs",
            self._corpus_path,
            len(self._descendant_counts),
            time.monotonic() - started_at,
        )
        logger.info(
            "Loaded clause corpus path=%s documents=%d clauses=%d elapsed=%.2fs",
            self._corpus_path,
            len(self._document_summaries),
            sum(len(items) for items in self._records_by_document.values()),
            time.monotonic() - started_at,
        )

    def _compute_descendant_counts(self, document_key: tuple[str, str, str], records: dict[str, ClauseRecord]) -> None:
        children_by_clause = self._children_by_document[document_key]
        counts: dict[str, int] = {}
        for clause_id, record in sorted(records.items(), key=lambda item: item[1].order_in_source, reverse=True):
            total = 0
            for child_id in children_by_clause.get(clause_id, []):
                total += 1 + counts.get(child_id, 0)
            counts[clause_id] = total
            self._descendant_counts[(record.key, clause_id)] = total

    def _get_records_for_document(self, spec_no: str, release_data: str, release: str) -> dict[str, ClauseRecord]:
        normalized_key = self._resolve_document_key(spec_no, release_data, release)
        if normalized_key is None:
            return {}
        return self._records_by_document.get(normalized_key, {})

    def _resolve_document_key(self, spec_no: str, release_data: str, release: str) -> tuple[str, str, str] | None:
        if release_data.strip() and release.strip():
            exact_key = self._document_key(spec_no, release_data.strip(), release.strip())
            if exact_key in self._records_by_document:
                return exact_key
        matches = [
            self._document_key(summary.spec_no, summary.release_data, summary.release)
            for summary in self._document_summaries
            if summary.spec_no == spec_no
        ]
        if not matches:
            return None
        return sorted(matches)[0]

    @staticmethod
    def _document_key(spec_no: str, release_data: str, release: str) -> tuple[str, str, str]:
        return (release_data.strip(), release.strip(), spec_no.strip())

    def _document_summary_matches_clause_query(self, summary: DocumentSummary, normalized_query: str) -> bool:
        records = self._get_records_for_document(summary.spec_no, summary.release_data, summary.release)
        for record in records.values():
            haystack = self._record_search_text(record)
            if normalized_query in haystack:
                return True
        return False

    def _record_search_text(self, record: ClauseRecord) -> str:
        block_parts: list[str] = []
        for block in record.blocks or ():
            if not isinstance(block, dict):
                continue
            block_type = str(block.get("type") or "")
            if block_type == "paragraph":
                block_parts.append(str(block.get("text") or ""))
                continue
            if block_type == "table":
                for row in block.get("rows") or []:
                    if isinstance(row, list):
                        block_parts.extend(str(cell or "") for cell in row)
                continue
            if block_type == "image":
                block_parts.append(str(block.get("caption") or ""))
                block_parts.append(str(block.get("alt") or ""))
        return " ".join(
            [
                record.clause_id,
                record.clause_title,
                record.text,
                " ".join(record.clause_path),
                " ".join(part for part in block_parts if part),
            ]
        ).casefold()

    def _build_tree(self, record: ClauseRecord) -> ClauseTreeNode:
        document_key = self._document_key(record.spec_no, record.release_data, record.release)
        child_ids = self._children_by_document[document_key].get(record.clause_id, [])
        children = tuple(self._build_tree(self._records_by_document[document_key][child_id]) for child_id in child_ids)
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
            descendant_count=self._descendant_counts[(record.key, record.clause_id)],
            blocks=record.blocks,
            children=children,
        )

    @staticmethod
    def _preview(text: str, max_chars: int = 180) -> str:
        normalized = " ".join((text or "").split())
        if len(normalized) <= max_chars:
            return normalized
        return normalized[: max_chars - 1].rstrip() + "..."


class ScopedClauseRepositoryManager:
    def __init__(self, corpus_root: str | Path, fallback_corpus_path: str | Path | None = None) -> None:
        self._corpus_root = Path(corpus_root)
        self._fallback_corpus_path = Path(fallback_corpus_path) if fallback_corpus_path else None
        self._cache: dict[tuple[str, str], ClauseRepository] = {}
        self._lock = threading.Lock()

    @property
    def corpus_path(self) -> Path:
        return self._corpus_root

    def list_release_scopes(self) -> list[dict[str, str]]:
        if not self._corpus_root.is_dir():
            return []
        scopes: list[dict[str, str]] = []
        for release_data_dir in sorted(self._corpus_root.iterdir()):
            if not release_data_dir.is_dir():
                continue
            for release_dir in sorted(release_data_dir.iterdir()):
                corpus_path = release_dir / "clause_browser_corpus.jsonl"
                if corpus_path.is_file():
                    scopes.append({"releaseData": release_data_dir.name, "release": release_dir.name})
        return scopes

    def list_documents(
        self,
        query: str = "",
        clause_query: str = "",
        limit: int = 50,
        release_data: str = "",
        release: str = "",
    ) -> list[DocumentSummary]:
        return self._get_repo_for_scope(release_data=release_data, release=release).list_documents(
            query=query,
            clause_query=clause_query,
            limit=limit,
            release_data=release_data,
            release=release,
        )

    def list_clauses(
        self,
        spec_no: str,
        query: str = "",
        limit: int = 100,
        include_all: bool = False,
        release_data: str = "",
        release: str = "",
    ) -> list[ClauseSummary]:
        return self._get_repo_for_scope(release_data=release_data, release=release).list_clauses(
            spec_no=spec_no,
            query=query,
            limit=limit,
            include_all=include_all,
        )

    def get_subtree(self, spec_no: str, clause_id: str, release_data: str = "", release: str = "") -> ClauseTreeNode:
        return self._get_repo_for_scope(release_data=release_data, release=release).get_subtree(spec_no=spec_no, clause_id=clause_id)

    def has_clause(self, spec_no: str, clause_id: str, release_data: str = "", release: str = "") -> bool:
        return self._get_repo_for_scope(release_data=release_data, release=release).has_clause(spec_no=spec_no, clause_id=clause_id)

    def _get_repo_for_scope(self, *, release_data: str, release: str) -> ClauseRepository:
        normalized_scope = (release_data.strip(), release.strip())
        if all(normalized_scope):
            with self._lock:
                cached = self._cache.get(normalized_scope)
                if cached is not None:
                    return cached
                corpus_path = self._corpus_root / normalized_scope[0] / normalized_scope[1] / "clause_browser_corpus.jsonl"
                if not corpus_path.is_file():
                    raise FileNotFoundError(f"Clause corpus not found for scope {normalized_scope[0]}/{normalized_scope[1]}: {corpus_path}")
                repository = ClauseRepository(corpus_path)
                self._cache[normalized_scope] = repository
                return repository
        if self._fallback_corpus_path and self._fallback_corpus_path.is_file():
            return ClauseRepository(self._fallback_corpus_path)
        raise FileNotFoundError("A release/date scope is required before loading the clause browser corpus.")
