from __future__ import annotations

import argparse

from app.main import (
    build_exclude_clause_pairs,
    build_exclusion_sets,
    build_release_filter_lists,
    filter_iterative_result,
    filter_vespa_response_children,
)


def test_build_exclusion_sets_ignores_invalid_values() -> None:
    args = argparse.Namespace(
        exclude_specs=[" 23501 ", "", "   "],
        exclude_clauses=["23501:5.1", "missing-delimiter", " :5.2", "23502: "],
    )

    excluded_specs, excluded_clause_pairs = build_exclusion_sets(args)

    assert excluded_specs == {"23501"}
    assert excluded_clause_pairs == {("23501", "5.1")}


def test_build_release_filter_lists_returns_none_for_empty_values() -> None:
    args = argparse.Namespace(
        release_filters=[" Rel-18 ", "", " "],
        release_data_filters=["", "2025-12"],
    )

    release_filters, release_data_filters = build_release_filter_lists(args)

    assert release_filters == ["Rel-18"]
    assert release_data_filters == ["2025-12"]


def test_build_exclude_clause_pairs_preserves_order_of_valid_items() -> None:
    args = argparse.Namespace(
        exclude_clauses=["23501:5.1", "invalid", "23502:4.2.2.2"],
    )

    assert build_exclude_clause_pairs(args) == [("23501", "5.1"), ("23502", "4.2.2.2")]


def test_filter_vespa_response_children_keeps_non_excluded_hits() -> None:
    response = {
        "root": {
            "children": [
                {"fields": {"spec_no": "23501", "clause_id": "5.1"}},
                {"fields": {"spec_no": "23502", "clause_id": "4.2.2.2"}},
            ]
        }
    }

    filtered = filter_vespa_response_children(response, {"23501"}, {("23502", "4.2.2.3")})

    assert filtered == {
        "root": {
            "children": [
                {"fields": {"spec_no": "23502", "clause_id": "4.2.2.2"}},
            ]
        }
    }


def test_filter_iterative_result_removes_excluded_documents() -> None:
    result = {
        "relevant_documents": [
            {"spec_no": "23501", "clause_id": "5.1"},
            {"spec_no": "23502", "clause_id": "4.2.2.2"},
        ]
    }

    filtered = filter_iterative_result(result, {"23501"}, {("23502", "4.2.2.3")})

    assert filtered == {
        "relevant_documents": [
            {"spec_no": "23502", "clause_id": "4.2.2.2"},
        ]
    }
