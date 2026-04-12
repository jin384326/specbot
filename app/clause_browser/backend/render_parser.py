from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.table import Table
from docx.text.paragraph import Paragraph
from docx.oxml.ns import qn

from parser.corpus_builder import convert_word_to_docx, is_legacy_word_document, is_supported_docx
from parser.docx_clause_parser import (
    _flatten_table_cells_row_major,
    clean_table_matrix,
    collect_toc_headings,
    iter_block_items,
    normalize_whitespace,
    normalize_table_cell_text,
    paragraph_outline_level,
    paragraph_style_level,
    TocHeading,
    split_relative_clause_heading,
    should_treat_paragraph_as_heading,
    split_clause_heading,
)


IMAGE_CONTENT_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/gif": ".gif",
    "image/bmp": ".bmp",
    "image/tiff": ".tiff",
    "image/webp": ".webp",
}

EMU_PER_PIXEL = 9525


@dataclass
class RenderClauseNode:
    key: str
    spec_no: str
    spec_title: str
    clause_id: str
    clause_title: str
    parent_clause_id: str
    clause_path: tuple[str, ...]
    source_file: str
    order_in_source: int
    blocks: list[dict[str, Any]] = field(default_factory=list)
    children: list["RenderClauseNode"] = field(default_factory=list)


class RichDocxClauseParser:
    def __init__(self, media_root: str | Path, media_mount_prefix: str = "/clause-browser-media") -> None:
        self._media_root = Path(media_root)
        self._media_root.mkdir(parents=True, exist_ok=True)
        self._media_mount_prefix = media_mount_prefix.rstrip("/")

    def parse_document(self, spec_no: str, spec_title: str, source_file: str) -> dict[str, RenderClauseNode]:
        path = Path(source_file)
        document = Document(str(path))
        toc_headings = collect_toc_headings(document)

        nodes: dict[str, RenderClauseNode] = {}
        clause_stack: list[RenderClauseNode] = []
        active_clause: RenderClauseNode | None = None
        clause_counter = 0
        paragraph_counter = 0
        seen_structured_clause = False

        for block in iter_block_items(document):
            if isinstance(block, Paragraph):
                text = normalize_whitespace(block.text)
                style_name = block.style.name if block.style else ""
                if style_name.lower().startswith("toc"):
                    continue

                heading_level = paragraph_style_level(style_name) or paragraph_outline_level(block)
                heading = split_clause_heading(text) if text else None
                if heading is None and heading_level is not None and text:
                    relative_heading = split_relative_clause_heading(text)
                    if relative_heading is not None:
                        heading = self._resolve_relative_heading(relative_heading, heading_level, clause_stack)
                if heading is None and heading_level is not None and text:
                    heading = self._resolve_toc_heading(text, heading_level, clause_stack, toc_headings)
                if heading is None and heading_level is not None and text:
                    heading = self._resolve_implicit_heading(text, heading_level, clause_stack)
                if not should_treat_paragraph_as_heading(style_name, text, heading_level, heading):
                    heading = None

                if heading_level is not None or heading is not None:
                    if not seen_structured_clause and heading is None:
                        continue
                    clause_counter += 1
                    paragraph_counter += 1
                    clause_id, clause_title, level = self._resolve_heading(text, heading_level, heading, clause_counter)
                    while clause_stack and clause_stack[-1].order_in_source >= 0 and self._level_for_node(clause_stack[-1]) >= level:
                        clause_stack.pop()
                    parent = clause_stack[-1] if clause_stack else None
                    clause_path = (*parent.clause_path, clause_id) if parent else (clause_id,)
                    node = RenderClauseNode(
                        key=f"{spec_no}:{clause_id}",
                        spec_no=spec_no,
                        spec_title=spec_title,
                        clause_id=clause_id,
                        clause_title=clause_title,
                        parent_clause_id=parent.clause_id if parent else "",
                        clause_path=clause_path,
                        source_file=source_file,
                        order_in_source=paragraph_counter,
                    )
                    nodes[clause_id] = node
                    if parent:
                        parent.children.append(node)
                    clause_stack.append(node)
                    active_clause = node
                    if not clause_id.startswith("heading_") and not clause_id.startswith("front_matter_"):
                        seen_structured_clause = True
                    continue

                if active_clause is None:
                    continue

                paragraph_counter += 1
                if text:
                    paragraph_block = {"type": "paragraph", "text": text}
                    paragraph_format = self._extract_paragraph_format(block)
                    if paragraph_format:
                        paragraph_block["format"] = paragraph_format
                    active_clause.blocks.append(paragraph_block)
                for image_block in self._extract_paragraph_images(block, spec_no, active_clause.clause_id):
                    active_clause.blocks.append(image_block)

            elif active_clause is not None:
                matrix = clean_table_matrix(block)
                if matrix:
                    active_clause.blocks.append(self._build_table_block(block, matrix))

        return nodes

    @staticmethod
    def _resolve_heading(
        text: str,
        heading_level: int | None,
        heading: tuple[str, str] | None,
        clause_counter: int,
    ) -> tuple[str, str, int]:
        if heading:
            clause_id, clause_title = heading
            return clause_id, clause_title, clause_id.count(".") + 1 if not clause_id.startswith("Annex ") else 1
        return f"heading_{clause_counter}", text, heading_level or 1

    @staticmethod
    def _resolve_relative_heading(
        heading: tuple[str, str],
        heading_level: int,
        clause_stack: list[RenderClauseNode],
    ) -> tuple[str, str] | None:
        if heading_level <= 1:
            return None
        parent = next((item for item in reversed(clause_stack) if len(item.clause_path) < heading_level), None)
        if parent is None:
            return None
        relative_clause_id, clause_title = heading
        return f"{parent.clause_id}.{relative_clause_id}", clause_title

    @staticmethod
    def _resolve_toc_heading(
        text: str,
        heading_level: int,
        clause_stack: list[RenderClauseNode],
        toc_headings: list[TocHeading],
    ) -> tuple[str, str] | None:
        normalized_text = normalize_whitespace(text)
        if not normalized_text:
            return None
        parent = next((item for item in reversed(clause_stack) if len(item.clause_path) < heading_level), None)
        parent_clause_id = parent.clause_id if parent else ""
        candidates = [
            item
            for item in toc_headings
            if item.level == heading_level and normalize_whitespace(item.clause_title) == normalized_text
        ]
        if not candidates:
            return None
        if parent_clause_id:
            parent_candidates = [item for item in candidates if item.parent_clause_id == parent_clause_id]
            if parent_candidates:
                candidates = parent_candidates
        if len(candidates) == 1:
            return candidates[0].clause_id, normalized_text
        return None

    @staticmethod
    def _resolve_implicit_heading(
        text: str,
        heading_level: int,
        clause_stack: list[RenderClauseNode],
    ) -> tuple[str, str] | None:
        if heading_level <= 1 or not clause_stack:
            return None
        parent = next((item for item in reversed(clause_stack) if len(item.clause_path) < heading_level), None)
        previous_same_level = next((item for item in reversed(clause_stack) if len(item.clause_path) == heading_level), None)
        if parent is None or previous_same_level is None:
            return None
        if previous_same_level.parent_clause_id != parent.clause_id:
            return None
        last_segment = previous_same_level.clause_id.split(".")[-1]
        if not last_segment.isdigit():
            return None
        return f"{parent.clause_id}.{int(last_segment) + 1}", text

    @staticmethod
    def _level_for_node(node: RenderClauseNode) -> int:
        return max(1, len(node.clause_path))

    def _extract_paragraph_images(self, paragraph: Paragraph, spec_no: str, clause_id: str) -> list[dict[str, Any]]:
        image_blocks: list[dict[str, Any]] = []
        relationship_refs: list[tuple[str, dict[str, int]]] = []
        for blip in paragraph._p.xpath(".//a:blip"):
            embed = blip.get(qn("r:embed"))
            if embed:
                relationship_refs.append((embed, self._extract_drawing_display_size(blip)))
        for imagedata in paragraph._p.xpath(".//*[local-name()='imagedata']"):
            rel_id = imagedata.get(qn("r:id"))
            if rel_id:
                relationship_refs.append((rel_id, self._extract_vml_display_size(imagedata)))

        seen: set[str] = set()
        for rel_id, display_size in relationship_refs:
            if rel_id in seen:
                continue
            seen.add(rel_id)
            image_part = paragraph.part.related_parts.get(rel_id)
            if image_part is None:
                continue
            extension = IMAGE_CONTENT_TYPES.get(getattr(image_part, "content_type", ""), Path(str(image_part.partname)).suffix or ".bin")
            digest = hashlib.sha1(image_part.blob).hexdigest()
            output_dir = self._media_root / spec_no / clause_id.replace("/", "_")
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = output_dir / f"{digest}{extension}"
            if not output_path.exists():
                output_path.write_bytes(image_part.blob)
            served_path = self._convert_vector_image_if_needed(output_path)
            image_block = {
                "type": "image",
                "src": f"{self._media_mount_prefix}/{spec_no}/{clause_id.replace('/', '_')}/{served_path.name}",
                "alt": normalize_whitespace(paragraph.text) or f"{clause_id} image",
            }
            image_block.update(display_size)
            image_blocks.append(image_block)
        return image_blocks

    @staticmethod
    def _extract_drawing_display_size(blip: Any) -> dict[str, int]:
        container = next(
            (
                ancestor
                for ancestor in blip.iterancestors()
                if ancestor.tag.endswith("}inline") or ancestor.tag.endswith("}anchor")
            ),
            None,
        )
        if container is None:
            return {}
        extent = next((child for child in container if child.tag.endswith("}extent")), None)
        if extent is None:
            return {}
        width = RichDocxClauseParser._emu_to_pixels(extent.get("cx"))
        height = RichDocxClauseParser._emu_to_pixels(extent.get("cy"))
        payload: dict[str, int] = {}
        if width:
            payload["displayWidthPx"] = width
        if height:
            payload["displayHeightPx"] = height
        return payload

    @staticmethod
    def _extract_vml_display_size(imagedata: Any) -> dict[str, int]:
        shape = next((ancestor for ancestor in imagedata.iterancestors() if ancestor.tag.endswith("}shape")), None)
        style = str(shape.get("style") or "") if shape is not None else ""
        if not style:
            return {}
        width = RichDocxClauseParser._style_length_to_pixels(style, "width")
        height = RichDocxClauseParser._style_length_to_pixels(style, "height")
        payload: dict[str, int] = {}
        if width:
            payload["displayWidthPx"] = width
        if height:
            payload["displayHeightPx"] = height
        return payload

    @staticmethod
    def _emu_to_pixels(value: Any) -> int:
        try:
            numeric = int(value)
        except (TypeError, ValueError):
            return 0
        if numeric <= 0:
            return 0
        return int(round(numeric / EMU_PER_PIXEL))

    @staticmethod
    def _style_length_to_pixels(style: str, property_name: str) -> int:
        match = re.search(rf"{re.escape(property_name)}\s*:\s*([0-9.]+)(pt|px|in|cm|mm)", style, flags=re.IGNORECASE)
        if not match:
            return 0
        value = float(match.group(1))
        unit = match.group(2).lower()
        if unit == "px":
            return int(round(value))
        if unit == "pt":
            return int(round(value * 96 / 72))
        if unit == "in":
            return int(round(value * 96))
        if unit == "cm":
            return int(round(value * 96 / 2.54))
        if unit == "mm":
            return int(round(value * 96 / 25.4))
        return 0

    @staticmethod
    def _extract_paragraph_format(paragraph: Paragraph) -> dict[str, float | int]:
        direct_format = paragraph.paragraph_format
        style_format = getattr(paragraph.style, "paragraph_format", None)
        style_name = paragraph.style.name if paragraph.style else ""
        alignment = paragraph.alignment

        left_indent_pt = RichDocxClauseParser._get_length_points(
            direct_format.left_indent,
            getattr(style_format, "left_indent", None),
        )
        first_line_indent_pt = RichDocxClauseParser._get_length_points(
            direct_format.first_line_indent,
            getattr(style_format, "first_line_indent", None),
        )

        left_indent_px = RichDocxClauseParser._points_to_pixels(left_indent_pt)
        text_indent_px = RichDocxClauseParser._points_to_pixels(first_line_indent_pt)

        payload: dict[str, float | int] = {}
        if left_indent_px:
            payload["leftIndentPx"] = left_indent_px
        if left_indent_pt:
            payload["leftIndentPt"] = round(left_indent_pt, 2)
        if text_indent_px:
            payload["textIndentPx"] = text_indent_px
        if first_line_indent_pt:
            payload["textIndentPt"] = round(first_line_indent_pt, 2)
        if style_name:
            payload["styleName"] = style_name
        if alignment is not None:
            payload["alignment"] = int(alignment)
        elif getattr(style_format, "alignment", None) is not None:
            payload["alignment"] = int(style_format.alignment)
        return payload

    @staticmethod
    def _get_length_points(*values: Any) -> float:
        for value in values:
            if value is None:
                continue
            try:
                return float(value.pt)
            except AttributeError:
                continue
        return 0.0

    @staticmethod
    def _points_to_pixels(value: float) -> int:
        if not value:
            return 0
        return int(round(value * 96 / 72))

    @staticmethod
    def _build_table_block(table: Table, matrix: list[list[str]]) -> dict[str, Any]:
        logical_col_count = max((len(row) for row in matrix), default=0)
        col_count = table._column_count
        if logical_col_count and logical_col_count != col_count:
            return {"type": "table", "rows": matrix}
        flat = _flatten_table_cells_row_major(table)
        if col_count <= 0 or not flat:
            return {"type": "table", "rows": matrix}

        nrows = len(flat) // col_count
        visited: set[tuple[int, int]] = set()
        rendered_rows: list[list[dict[str, Any]]] = []

        for row_idx in range(nrows):
            row_out: list[dict[str, Any]] = []
            for col_idx in range(col_count):
                if (row_idx, col_idx) in visited:
                    continue
                cell = flat[row_idx * col_count + col_idx]
                colspan = 1
                while col_idx + colspan < col_count and flat[row_idx * col_count + col_idx + colspan] is cell:
                    colspan += 1

                rowspan = 1
                while row_idx + rowspan < nrows:
                    next_row_matches = True
                    for offset in range(colspan):
                        if flat[(row_idx + rowspan) * col_count + col_idx + offset] is not cell:
                            next_row_matches = False
                            break
                    if not next_row_matches:
                        break
                    rowspan += 1

                for row_offset in range(rowspan):
                    for col_offset in range(colspan):
                        visited.add((row_idx + row_offset, col_idx + col_offset))

                row_out.append(
                    {
                        "text": normalize_table_cell_text(cell.text),
                        "rowspan": rowspan,
                        "colspan": colspan,
                        "header": row_idx == 0,
                    }
                )
            if row_out:
                rendered_rows.append(row_out)

        return {
            "type": "table",
            "rows": matrix,
            "cells": rendered_rows,
            "columnCount": col_count,
        }

    def _convert_vector_image_if_needed(self, path: Path) -> Path:
        suffix = path.suffix.lower()
        if suffix not in {".wmf", ".emf"}:
            return path

        description = self._describe_file(path)
        normalized_description = description.lower()
        if "enhanced metafile" in normalized_description:
            svg_path = path.with_suffix(".svg")
            if svg_path.exists():
                self._normalize_svg(svg_path)
                return svg_path
            temp_emf = path.with_suffix(".emf")
            if not temp_emf.exists():
                shutil.copyfile(path, temp_emf)
            self._run_inkscape(temp_emf, svg_path)
            self._normalize_svg(svg_path)
            return svg_path if svg_path.exists() else path

        if "windows metafile" in normalized_description:
            svg_path = path.with_suffix(".svg")
            if svg_path.exists():
                self._normalize_svg(svg_path)
                return svg_path
            self._run_wmf2svg(path, svg_path)
            self._normalize_svg(svg_path)
            return svg_path if svg_path.exists() else path

        return path

    @staticmethod
    def _describe_file(path: Path) -> str:
        try:
            result = subprocess.run(
                ["file", str(path)],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            return result.stdout
        except OSError:
            return ""

    @staticmethod
    def _run_inkscape(source_path: Path, output_path: Path) -> None:
        env = dict(os.environ)
        env.setdefault("HOME", "/tmp/specbothome")
        env.setdefault("XDG_RUNTIME_DIR", "/tmp/specbotruntime")
        Path(env["HOME"]).mkdir(parents=True, exist_ok=True)
        Path(env["XDG_RUNTIME_DIR"]).mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["inkscape", str(source_path), "--export-type=svg", f"--export-filename={output_path}"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )

    @staticmethod
    def _run_wmf2svg(source_path: Path, output_path: Path) -> None:
        subprocess.run(
            ["wmf2svg", "-o", str(output_path), str(source_path)],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    @staticmethod
    def _normalize_svg(path: Path) -> None:
        if not path.exists():
            return
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return
        if "<svg" not in text or 'xmlns="http://www.w3.org/2000/svg"' in text:
            return
        normalized = text.replace("<svg ", '<svg xmlns="http://www.w3.org/2000/svg" ', 1)
        if normalized == text:
            return
        try:
            path.write_text(normalized, encoding="utf-8")
        except OSError:
            return


class RichClauseDocumentService:
    def __init__(self, base_repository, media_root: str | Path, media_mount_prefix: str = "/clause-browser-media") -> None:
        self._base_repository = base_repository
        self._parser = RichDocxClauseParser(media_root=media_root, media_mount_prefix=media_mount_prefix)
        self._media_root = Path(media_root)
        self._cache: dict[str, dict[str, RenderClauseNode]] = {}
        self._resolved_source_cache: dict[str, Path] = {}

    def get_subtree(self, spec_no: str, clause_id: str):
        nodes = self._get_nodes(spec_no)
        if clause_id not in nodes:
            raise KeyError(f"Unknown clause: {spec_no}:{clause_id}")
        return self._to_tree(nodes[clause_id])

    def _get_nodes(self, spec_no: str) -> dict[str, RenderClauseNode]:
        if spec_no in self._cache:
            return self._cache[spec_no]
        summary = self._base_repository.get_document_summary(spec_no)
        source_path = self._resolve_source_path(summary.source_file)
        nodes = self._parser.parse_document(spec_no=summary.spec_no, spec_title=summary.spec_title, source_file=str(source_path))
        self._cache[spec_no] = nodes
        return nodes

    def _resolve_source_path(self, source_file: str) -> Path:
        cached = self._resolved_source_cache.get(source_file)
        if cached is not None:
            return cached

        source_path = Path(source_file)
        if is_supported_docx(source_path):
            resolved_path = source_path
        elif is_legacy_word_document(source_path):
            converted_root = self._media_root / ".converted_docx"
            expected = converted_root / hashlib.sha1(str(source_path.resolve()).encode("utf-8")).hexdigest()[:12] / f"{source_path.stem}.docx"
            if expected.exists():
                resolved_path = expected
            else:
                converted = convert_word_to_docx(source_path, converted_root)
                if converted is None and expected.exists():
                    resolved_path = expected
                elif converted is None:
                    raise FileNotFoundError(f"Unable to convert legacy Word document: {source_path}")
                else:
                    resolved_path = converted
        elif source_path.with_suffix(".docx").exists():
            resolved_path = source_path.with_suffix(".docx")
        else:
            raise FileNotFoundError(f"Package not found at '{source_path}'")

        self._resolved_source_cache[source_file] = resolved_path
        return resolved_path

    def _to_tree(self, node: RenderClauseNode):
        from app.clause_browser.backend.domain import ClauseTreeNode

        descendants = self._count_descendants(node)
        return ClauseTreeNode(
            key=node.key,
            spec_no=node.spec_no,
            spec_title=node.spec_title,
            clause_id=node.clause_id,
            clause_title=node.clause_title,
            text="\n".join(block["text"] for block in node.blocks if block["type"] == "paragraph").strip(),
            parent_clause_id=node.parent_clause_id,
            clause_path=node.clause_path,
            source_file=node.source_file,
            order_in_source=node.order_in_source,
            child_count=len(node.children),
            descendant_count=descendants,
            blocks=tuple(node.blocks),
            children=tuple(self._to_tree(child) for child in node.children),
        )

    def _count_descendants(self, node: RenderClauseNode) -> int:
        return sum(1 + self._count_descendants(child) for child in node.children)
