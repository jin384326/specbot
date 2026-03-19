from __future__ import annotations

from retrieval.llm_selector import HeuristicSelectionLLM, OpenAISelectionLLM


def test_heuristic_selector_returns_known_candidate_ids_only() -> None:
    selector = HeuristicSelectionLLM()
    spec_ids = selector.select_specs(
        "PDU Session Establishment procedure",
        [{"spec_id": "23501"}, {"spec_id": "23502"}],
        limit=1,
    )
    candidate_ids = selector.judge_relevance(
        "PDU Session Establishment procedure",
        [{"doc_id": "d1"}, {"doc_id": "d2"}],
        limit=1,
    )
    anchor_ids = selector.select_anchors(
        "PDU Session Establishment procedure",
        [{"anchor_id": "a1"}, {"anchor_id": "a2"}],
        limit=1,
    )

    assert spec_ids == ["23501"]
    assert candidate_ids == ["d1"]
    assert anchor_ids == ["a1"]


def test_openai_selector_extract_output_text_from_response_shapes() -> None:
    response = {
        "output": [
            {
                "content": [
                    {
                        "text": "{\"selected_doc_ids\": [\"d1\"], \"selected_anchor_ids\": [\"a1\"]}",
                    }
                ]
            }
        ]
    }

    assert OpenAISelectionLLM._extract_output_text(response) == "{\"selected_doc_ids\": [\"d1\"], \"selected_anchor_ids\": [\"a1\"]}"
