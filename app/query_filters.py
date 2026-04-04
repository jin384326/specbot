from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_metadata_map(path: str | None) -> dict[str, dict]:
    if path is None:
        return {}
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def build_exclusion_sets(args: argparse.Namespace) -> tuple[set[str], set[tuple[str, str]]]:
    excluded_specs = {str(item).strip() for item in getattr(args, "exclude_specs", []) or [] if str(item).strip()}
    excluded_clause_pairs: set[tuple[str, str]] = set()
    for item in getattr(args, "exclude_clauses", []) or []:
        raw = str(item).strip()
        if not raw or ":" not in raw:
            continue
        spec_no, clause_id = raw.split(":", maxsplit=1)
        spec_no = spec_no.strip()
        clause_id = clause_id.strip()
        if spec_no and clause_id:
            excluded_clause_pairs.add((spec_no, clause_id))
    return excluded_specs, excluded_clause_pairs


def build_release_filter_lists(args: argparse.Namespace) -> tuple[list[str] | None, list[str] | None]:
    release_filters = [str(item).strip() for item in getattr(args, "release_filters", []) or [] if str(item).strip()]
    release_data_filters = [str(item).strip() for item in getattr(args, "release_data_filters", []) or [] if str(item).strip()]
    return (release_filters or None, release_data_filters or None)


def build_exclude_clause_pairs(args: argparse.Namespace) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for item in getattr(args, "exclude_clauses", []) or []:
        raw = str(item).strip()
        if not raw or ":" not in raw:
            continue
        spec_no, clause_id = raw.split(":", maxsplit=1)
        normalized_spec = spec_no.strip()
        normalized_clause = clause_id.strip()
        if normalized_spec and normalized_clause:
            pairs.append((normalized_spec, normalized_clause))
    return pairs


def is_excluded_hit(spec_no: str, clause_id: str, excluded_specs: set[str], excluded_clause_pairs: set[tuple[str, str]]) -> bool:
    normalized_spec = str(spec_no).strip()
    normalized_clause = str(clause_id).strip()
    if not normalized_clause:
        return True
    return normalized_spec in excluded_specs or (normalized_spec, normalized_clause) in excluded_clause_pairs


def filter_vespa_response_children(
    response: dict[str, object],
    excluded_specs: set[str],
    excluded_clause_pairs: set[tuple[str, str]],
) -> dict[str, object]:
    root = dict(response.get("root", {}))
    children = list(root.get("children", []) or [])
    filtered_children = []
    for child in children:
        fields = child.get("fields", {}) if isinstance(child, dict) else {}
        if is_excluded_hit(fields.get("spec_no", ""), fields.get("clause_id", ""), excluded_specs, excluded_clause_pairs):
            continue
        filtered_children.append(child)
    root["children"] = filtered_children
    return {**response, "root": root}


def filter_iterative_result(
    result: dict[str, object],
    excluded_specs: set[str],
    excluded_clause_pairs: set[tuple[str, str]],
) -> dict[str, object]:
    relevant_documents = [
        item
        for item in list(result.get("relevant_documents", []) or [])
        if not is_excluded_hit(item.get("spec_no", ""), item.get("clause_id", ""), excluded_specs, excluded_clause_pairs)
    ]
    return {**result, "relevant_documents": relevant_documents}
