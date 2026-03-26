from __future__ import annotations

import logging
from pathlib import Path

from parser.models import ClauseDoc
from retrieval.iterative_llm_retriever import (
    ChatOpenAIRelevanceJudge,
    IterativeLLMRetriever,
    KeywordExtraction,
    RelevanceDecision,
    RetrievalCancelledError,
    SummaryDecision,
)
from retrieval.multi_hop_pipeline import MultiHopSearchHit


class StubBackend:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, int]] = []

    def search(self, terms, limit=20, stage_filters=None, spec_filters=None):
        del spec_filters
        query = next(iter(terms))
        stage = stage_filters[0] if stage_filters else ""
        self.calls.append((query, stage, limit))
        score = {"stage2": 3.0, "stage3": 2.0, "else": 1.0}[stage]
        doc = ClauseDoc(
            doc_id=f"{query}:{stage}",
            spec_no="23501",
            stage_hint=stage,
            clause_id="1",
            parent_clause_id="0",
            clause_path=["0", "1"],
            clause_title=f"{query} {stage}",
            text=f"{query} procedure in {stage}",
            summary=f"{query} summary {stage}",
        )
        return [MultiHopSearchHit(doc=doc, score=score, reason_type="vespa_hit", matched_text=query, metadata={})]


class DuplicateDocBackend:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, int]] = []

    def search(self, terms, limit=20, stage_filters=None, spec_filters=None):
        del spec_filters, limit
        query = next(iter(terms))
        stage = stage_filters[0] if stage_filters else ""
        self.calls.append((query, stage, 0))
        doc = ClauseDoc(
            doc_id="registration-shared-doc",
            spec_no="23501",
            stage_hint=stage,
            clause_id="1",
            parent_clause_id="0",
            clause_path=["0", "1"],
            clause_title=f"{query} {stage}",
            text=f"{query} procedure in {stage}",
            summary=f"{query} summary {stage}",
        )
        return [MultiHopSearchHit(doc=doc, score=1.0, reason_type="vespa_hit", matched_text=query, metadata={})]


class DuplicateTextDifferentDocIdBackend:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, int]] = []

    def search(self, terms, limit=20, stage_filters=None, spec_filters=None):
        del spec_filters, limit
        query = next(iter(terms))
        stage = stage_filters[0] if stage_filters else ""
        self.calls.append((query, stage, 0))
        doc_id = "registration-doc-a" if stage in {"stage2", "stage3"} else "registration-doc-b"
        doc = ClauseDoc(
            doc_id=doc_id,
            spec_no="23501",
            stage_hint=stage,
            clause_id="1",
            parent_clause_id="0",
            clause_path=["0", "1"],
            clause_title="Same Title",
            text="Same body content across different doc ids",
            summary="Same summary content",
        )
        return [MultiHopSearchHit(doc=doc, score=1.0, reason_type="vespa_hit", matched_text=query, metadata={})]


class ClauseLookupBackend(StubBackend):
    def __init__(self) -> None:
        super().__init__()
        self.lookup_calls: list[tuple[str, str, int]] = []

    def lookup_clause(self, spec_no: str, clause_id: str, limit: int = 20, stage_filters=None):
        del stage_filters
        self.lookup_calls.append((spec_no, clause_id, limit))
        doc = ClauseDoc(
            doc_id=f"{spec_no}:{clause_id}",
            spec_no=spec_no,
            stage_hint="stage2",
            clause_id=clause_id,
            parent_clause_id="5.2.2",
            clause_path=["5", "5.2", "5.2.2", clause_id],
            clause_title=f"Clause {clause_id}",
            text=f"Direct lookup for clause {clause_id}",
            summary=f"Direct clause {clause_id}",
        )
        return [MultiHopSearchHit(doc=doc, score=99.0, reason_type="clause_reference", matched_text=clause_id, metadata={})]


class StubJudge:
    def __init__(self) -> None:
        self.relevance_calls: list[tuple[str, list[str]]] = []
        self.keyword_calls: list[tuple[str, list[str]]] = []

    def judge_relevance(self, query_text: str, candidates: list[dict]) -> list[dict]:
        self.relevance_calls.append((query_text, [str(item["doc_id"]) for item in candidates]))
        results = []
        for item in candidates:
            relevant = item["doc_id"].startswith("registration")
            results.append(
                {
                    "doc_id": item["doc_id"],
                    "is_relevant": relevant,
                    "reason": "matched registration flow" if relevant else "not relevant",
                }
            )
        return results

    def extract_keywords(self, query_text: str, relevant_candidates: list[dict], keyword_limit: int = 5) -> list[dict]:
        del keyword_limit
        self.keyword_calls.append((query_text, [str(item["doc_id"]) for item in relevant_candidates]))
        return [
            {
                "doc_id": item["doc_id"],
                "keywords": ["amf registration", "ue context"],
                "reason": "keyword match",
            }
            for item in relevant_candidates
        ]


def test_iterative_retriever_runs_stage_fanout_and_keyword_expansion() -> None:
    backend = StubBackend()
    judge = StubJudge()
    retriever = IterativeLLMRetriever(backend=backend, evaluator=judge)

    result = retriever.run("registration", limit=2, iterations=2)

    assert result["query"] == "registration"
    assert result["iterations_requested"] == 2
    assert len(result["iterations"]) == 2
    assert backend.calls[:3] == [
        ("registration", "stage2", 2),
        ("registration", "stage3", 2),
        ("registration", "else", 2),
    ]
    assert backend.calls[3:] == [
        ("amf registration", "stage2", 2),
        ("amf registration", "stage3", 2),
        ("amf registration", "else", 2),
        ("ue context", "stage2", 2),
        ("ue context", "stage3", 2),
        ("ue context", "else", 2),
        ("registration stage2", "stage2", 2),
        ("registration stage2", "stage3", 2),
        ("registration stage2", "else", 2),
        ("registration stage3", "stage2", 2),
        ("registration stage3", "stage3", 2),
        ("registration stage3", "else", 2),
        ("registration else", "stage2", 2),
        ("registration else", "stage3", 2),
        ("registration else", "else", 2),
    ]
    expanded_terms = [call[0] for call in backend.calls[3:]]
    assert expanded_terms == [
        "amf registration", "amf registration", "amf registration",
        "ue context", "ue context", "ue context",
        "registration stage2", "registration stage2", "registration stage2",
        "registration stage3", "registration stage3", "registration stage3",
        "registration else", "registration else", "registration else",
    ]
    assert all(item["judgement"]["is_relevant"] for item in result["all_results"][:3])
    assert result["all_results"][0]["search_term"] == "registration"
    assert result["all_results"][0]["parent_clause_id"] == "0"
    assert result["all_results"][0]["clause_path"] == ["0", "1"]
    assert len(result["relevant_documents"]) == 1
    relevant_doc = result["relevant_documents"][0]
    assert relevant_doc["doc_id"] == "registration:stage2"
    assert relevant_doc["spec_no"] == "23501"
    assert relevant_doc["clause_id"] == "1"
    assert relevant_doc["parent_clause_id"] == "0"
    assert relevant_doc["clause_path"] == ["0", "1"]
    assert "registration procedure in stage2" in relevant_doc["texts"]
    assert "registration procedure in stage3" in relevant_doc["texts"]
    assert "registration procedure in else" in relevant_doc["texts"]
    assert result["collected_keywords"] == ["amf registration", "ue context"]
    assert judge.relevance_calls[0][1] == ["registration:stage2", "registration:stage3", "registration:else"]
    assert judge.keyword_calls == [("registration", ["registration:stage2", "registration:stage3", "registration:else"])]
    assert result["iterations"][0]["next_search_terms"] == [
        "amf registration",
        "ue context",
        "registration stage2",
        "registration stage3",
        "registration else",
    ]


def test_iterative_retriever_stops_early_when_no_keywords_returned() -> None:
    backend = StubBackend()

    class EmptyJudge:
        def judge_relevance(self, query_text: str, candidates: list[dict]) -> list[dict]:
            del query_text
            return [{"doc_id": item["doc_id"], "is_relevant": False, "reason": "none"} for item in candidates]

        def extract_keywords(self, query_text: str, relevant_candidates: list[dict], keyword_limit: int = 5) -> list[dict]:
            del query_text, relevant_candidates, keyword_limit
            return []

    retriever = IterativeLLMRetriever(backend=backend, evaluator=EmptyJudge())

    result = retriever.run("paging", limit=1, iterations=3)

    assert len(result["iterations"]) == 1


def test_iterative_retriever_can_be_cancelled_between_iterations() -> None:
    backend = StubBackend()
    judge = StubJudge()
    retriever = IterativeLLMRetriever(backend=backend, evaluator=judge)

    calls = {"count": 0}

    def should_cancel() -> bool:
        calls["count"] += 1
        return calls["count"] > 1

    try:
        retriever.run("registration", limit=2, iterations=3, should_cancel=should_cancel)
        assert False, "Expected RetrievalCancelledError"
    except RetrievalCancelledError:
        pass


def test_chatopenai_relevance_judge_filters_unknown_doc_ids_and_normalizes_keywords() -> None:
    judge = ChatOpenAIRelevanceJudge.__new__(ChatOpenAIRelevanceJudge)
    judge.model = "gpt-4o-mini"
    judge.temperature = 0.0
    judge.timeout = 30
    judge.api_key = "test"
    judge._llm = None
    judge._keyword_llm = None
    judge._summary_llm = None
    judge.relevance_system_prompt_path = Path("system_prompt_relevance.txt")
    judge.relevance_user_prompt_path = Path("user_prompt_relevance.txt")
    judge.feature_system_prompt_path = Path("system_prompt_feature_anchor.txt")
    judge.feature_user_prompt_path = Path("user_propt_feature_anchor.txt")

    class StubRelevanceLLM:
        def invoke(self, payload) -> RelevanceDecision:
            system_message = payload[0][1]
            user_message = payload[1][1]
            assert "strict 3GPP retrieval relevance judge" in system_message
            assert "Original user query: registration" in user_message
            assert "Current retrieval keyword: registration" in user_message or "Current retrieval keyword: amf registration" in user_message
            assert "doc_id: d1" in user_message or "doc_id: d2" in user_message
            if "doc_id: d1" in user_message:
                return RelevanceDecision(doc_id="d1", is_relevant=True, reason="match")
            return RelevanceDecision(doc_id="missing", is_relevant=True, reason="bad")

    class StubKeywordLLM:
        def invoke(self, payload) -> KeywordExtraction:
            system_message = payload[0][1]
            user_message = payload[1][1]
            assert "feature-anchor extractor" in system_message
            assert "Keyword limit: 2" in user_message
            if "doc_id: d1" in user_message:
                return KeywordExtraction(doc_id="d1", keywords=["amf", "AMF", " ue context "], reason="keyword-match")
            return KeywordExtraction(doc_id="missing", keywords=["ignore"], reason="bad")

    judge._relevance_llm = StubRelevanceLLM()
    judge._keyword_llm = StubKeywordLLM()

    relevances = judge.judge_relevance(
        "registration",
        [
            {"doc_id": "d1", "context": "AMF registration context", "search_term": "amf registration"},
            {"doc_id": "d2", "context": "Other context", "search_term": "registration"},
        ],
    )
    keywords = judge.extract_keywords(
        "registration",
        [{"doc_id": "d1", "context": "AMF registration context"}],
        keyword_limit=2,
    )

    assert relevances == [
        {"doc_id": "d1", "is_relevant": True, "keywords": [], "reason": "match"},
        {"doc_id": "d2", "is_relevant": True, "keywords": [], "reason": "bad"},
    ]
    assert keywords == [{"doc_id": "d1", "keywords": ["amf", "ue context"], "reason": "keyword-match"}]


def test_chatopenai_relevance_judge_uses_sentence_summary_prompt_when_configured() -> None:
    judge = ChatOpenAIRelevanceJudge.__new__(ChatOpenAIRelevanceJudge)
    judge.model = "gpt-4o-mini"
    judge.temperature = 0.0
    judge.timeout = 30
    judge.api_key = "test"
    judge.extraction_mode = "sentence-summary"
    judge._llm = None
    judge._relevance_llm = None
    judge._keyword_llm = None
    judge.relevance_system_prompt_path = Path("system_prompt_relevance.txt")
    judge.relevance_user_prompt_path = Path("user_prompt_relevance.txt")
    judge.feature_system_prompt_path = Path("system_prompt_feature_anchor.txt")
    judge.feature_user_prompt_path = Path("user_propt_feature_anchor.txt")
    judge.followup_system_prompt_path = Path("system_prompt_followup_summary.txt")
    judge.followup_user_prompt_path = Path("user_prompt_followup_summary.txt")

    class StubSentenceLLM:
        def invoke(self, payload) -> SummaryDecision:
            system_message = payload[0][1]
            user_message = payload[1][1]
            assert "next-hop" in system_message
            assert "summarizer" in system_message or "summary sentence" in system_message
            assert "Follow-up sentence limit: 2" in user_message
            return SummaryDecision(
                doc_id="d1",
                summary_sentences=["Detailed sentence for next hop", "Another follow-up sentence"],
                reason="sentence follow-up",
            )

    judge._summary_llm = StubSentenceLLM()

    keywords = judge.extract_keywords(
        "registration",
        [{"doc_id": "d1", "context": "AMF registration context"}],
        keyword_limit=2,
    )

    assert keywords == [
        {
            "doc_id": "d1",
            "keywords": ["Detailed sentence for next hop", "Another follow-up sentence"],
            "reason": "sentence follow-up",
        }
    ]


def test_chatopenai_relevance_judge_wraps_structured_output_errors() -> None:
    judge = ChatOpenAIRelevanceJudge.__new__(ChatOpenAIRelevanceJudge)
    judge.model = "gpt-4o-mini"
    judge.temperature = 0.0
    judge.timeout = 30
    judge.api_key = "test"
    judge._llm = None
    judge._keyword_llm = None
    judge._summary_llm = None
    judge.relevance_system_prompt_path = Path("system_prompt_relevance.txt")
    judge.relevance_user_prompt_path = Path("user_prompt_relevance.txt")
    judge.feature_system_prompt_path = Path("system_prompt_feature_anchor.txt")
    judge.feature_user_prompt_path = Path("user_propt_feature_anchor.txt")

    class FailingStructuredLLM:
        def invoke(self, payload: str):
            del payload
            raise ValueError("schema validation failed")

    judge._relevance_llm = FailingStructuredLLM()

    try:
        judge.judge_relevance("registration", [{"doc_id": "d1", "context": "ctx"}])
    except RuntimeError as exc:
        assert "ChatOpenAI relevance judgement failed" in str(exc)
        assert "schema validation failed" in str(exc)
    else:
        raise AssertionError("RuntimeError was expected")

    judge._relevance_llm = None
    judge._keyword_llm = FailingStructuredLLM()
    try:
        judge.extract_keywords("registration", [{"doc_id": "d1", "context": "ctx"}])
    except RuntimeError as exc:
        assert "ChatOpenAI keyword extraction failed" in str(exc)
        assert "schema validation failed" in str(exc)
    else:
        raise AssertionError("RuntimeError was expected")


def test_iterative_retriever_emits_debug_logs(caplog) -> None:
    backend = StubBackend()
    judge = StubJudge()
    retriever = IterativeLLMRetriever(backend=backend, evaluator=judge)

    with caplog.at_level(logging.DEBUG, logger="retrieval.iterative_llm_retriever"):
        retriever.run("registration", limit=1, iterations=1)

    messages = [record.getMessage() for record in caplog.records]
    assert any("Iterative retrieval start" in message for message in messages)
    assert any("Searching Vespa" in message for message in messages)
    assert any("Iteration 1 complete" in message for message in messages)


def test_iterative_retriever_skips_duplicate_docs_and_reused_keywords() -> None:
    backend = DuplicateDocBackend()
    judge = StubJudge()
    retriever = IterativeLLMRetriever(backend=backend, evaluator=judge)

    result = retriever.run("registration", limit=2, iterations=3)

    assert len(result["all_results"]) == 1
    assert result["relevant_documents"] == [
        {
            "doc_id": "registration-shared-doc",
            "spec_no": "23501",
            "clause_id": "1",
            "parent_clause_id": "0",
            "clause_path": ["0", "1"],
            "texts": ["registration procedure in stage2"],
        }
    ]
    assert result["collected_keywords"] == ["amf registration", "ue context"]
    assert judge.relevance_calls == [("registration", ["registration-shared-doc"])]
    assert judge.keyword_calls == [("registration", ["registration-shared-doc"])]
    assert result["iterations"][0]["next_search_terms"] == ["amf registration", "ue context", "registration stage2"]
    assert len(result["iterations"]) == 1


def test_iterative_retriever_skips_same_text_with_different_doc_ids() -> None:
    backend = DuplicateTextDifferentDocIdBackend()
    judge = StubJudge()
    retriever = IterativeLLMRetriever(backend=backend, evaluator=judge)

    result = retriever.run("registration", limit=2, iterations=2)

    assert len(result["all_results"]) == 1
    assert result["relevant_documents"] == [
        {
            "doc_id": "registration-doc-a",
            "spec_no": "23501",
            "clause_id": "1",
            "parent_clause_id": "0",
            "clause_path": ["0", "1"],
            "texts": ["Same body content across different doc ids"],
        }
    ]
    assert result["collected_keywords"] == ["amf registration", "ue context"]
    assert judge.relevance_calls == [("registration", ["registration-doc-a"])]
    assert judge.keyword_calls == [("registration", ["registration-doc-a"])]


def test_iterative_retriever_resolves_clause_keywords_as_direct_candidates() -> None:
    backend = ClauseLookupBackend()

    class ClauseJudge(StubJudge):
        def extract_keywords(self, query_text: str, relevant_candidates: list[dict], keyword_limit: int = 5) -> list[dict]:
            del query_text, keyword_limit
            self.keyword_calls.append(("registration", [str(item["doc_id"]) for item in relevant_candidates]))
            if not relevant_candidates:
                return []
            return [
                {
                    "doc_id": relevant_candidates[0]["doc_id"],
                    "keywords": ["5.2.2.2", "5.2.2.3 of TS 23.501"],
                    "reason": "clause refs",
                }
            ]

    judge = ClauseJudge()
    retriever = IterativeLLMRetriever(backend=backend, evaluator=judge)

    result = retriever.run("registration", limit=2, iterations=2)

    assert backend.lookup_calls == [("23501", "5.2.2.2", 2), ("23501", "5.2.2.3", 2)]
    assert any(item["doc_id"] == "23501:5.2.2.2" for item in result["all_results"])
    assert any(item["doc_id"] == "23501:5.2.2.3" for item in result["all_results"])
    assert len(result["relevant_documents"]) == 1
    relevant_doc = result["relevant_documents"][0]
    assert relevant_doc["doc_id"] == "registration:stage2"
    assert relevant_doc["spec_no"] == "23501"
    assert relevant_doc["clause_id"] == "1"
    assert "registration procedure in stage2" in relevant_doc["texts"]
    assert "registration procedure in stage3" in relevant_doc["texts"]
    assert "registration procedure in else" in relevant_doc["texts"]
    assert result["iterations"][0]["next_search_terms"] == [
        "registration stage2",
        "registration stage3",
        "registration else",
    ]
    assert result["iterations"][0]["next_clause_targets"] == [
        {"spec_no": "23501", "clause_id": "5.2.2.2"},
        {"spec_no": "23501", "clause_id": "5.2.2.3"},
    ]
    assert result["collected_keywords"] == ["5.2.2.2", "5.2.2.3 of TS 23.501"]


def test_iterative_retriever_uses_custom_next_iteration_limit() -> None:
    backend = StubBackend()
    judge = StubJudge()
    retriever = IterativeLLMRetriever(backend=backend, evaluator=judge)

    retriever.run("registration", limit=4, iterations=2, next_iteration_limit=1)

    assert backend.calls[:3] == [
        ("registration", "stage2", 4),
        ("registration", "stage3", 4),
        ("registration", "else", 4),
    ]
    assert backend.calls[3:] == [
        ("amf registration", "stage2", 1),
        ("amf registration", "stage3", 1),
        ("amf registration", "else", 1),
        ("ue context", "stage2", 1),
        ("ue context", "stage3", 1),
        ("ue context", "else", 1),
        ("registration stage2", "stage2", 1),
        ("registration stage2", "stage3", 1),
        ("registration stage2", "else", 1),
        ("registration stage3", "stage2", 1),
        ("registration stage3", "stage3", 1),
        ("registration stage3", "else", 1),
        ("registration else", "stage2", 1),
        ("registration else", "stage3", 1),
        ("registration else", "else", 1),
    ]


def test_collect_next_actions_dedupes_duplicate_clause_titles() -> None:
    retriever = IterativeLLMRetriever(backend=StubBackend(), evaluator=StubJudge())

    next_terms, clause_targets = retriever._collect_next_actions(
        [
            {
                "spec_no": "23501",
                "clause_title": "Shared Clause Title",
                "judgement": {"is_relevant": True, "keywords": ["anchor a"]},
            },
            {
                "spec_no": "29502",
                "clause_title": "Shared Clause Title",
                "judgement": {"is_relevant": True, "keywords": ["anchor b"]},
            },
        ],
        seen_search_terms=set(),
        seen_clause_targets=set(),
    )

    assert next_terms == ["anchor a", "anchor b", "Shared Clause Title"]
    assert clause_targets == []


def test_collect_next_actions_skips_generic_clause_titles() -> None:
    retriever = IterativeLLMRetriever(backend=StubBackend(), evaluator=StubJudge())

    next_terms, clause_targets = retriever._collect_next_actions(
        [
            {
                "spec_no": "23501",
                "clause_title": "General",
                "judgement": {"is_relevant": True, "keywords": ["anchor a"]},
            },
            {
                "spec_no": "23501",
                "clause_title": "Overview",
                "judgement": {"is_relevant": True, "keywords": ["anchor b"]},
            },
            {
                "spec_no": "23501",
                "clause_title": "Specific Session Handling",
                "judgement": {"is_relevant": True, "keywords": []},
            },
        ],
        seen_search_terms=set(),
        seen_clause_targets=set(),
    )

    assert next_terms == ["anchor a", "anchor b", "Specific Session Handling"]
    assert clause_targets == []


def test_extract_relevant_documents_merges_texts_for_same_spec_and_clause() -> None:
    retriever = IterativeLLMRetriever(backend=StubBackend(), evaluator=StubJudge())

    extracted = retriever._extract_relevant_documents(
        [
            {
                "doc_id": "doc-a",
                "spec_no": "23501",
                "clause_id": "5.1",
                "parent_clause_id": "5",
                "clause_path": ["5", "5.1"],
                "text": "First text",
                "judgement": {"is_relevant": True},
            },
            {
                "doc_id": "doc-b",
                "spec_no": "23501",
                "clause_id": "5.1",
                "parent_clause_id": "5",
                "clause_path": ["5", "5.1"],
                "text": "Second text",
                "judgement": {"is_relevant": True},
            },
            {
                "doc_id": "doc-c",
                "spec_no": "23501",
                "clause_id": "5.1",
                "parent_clause_id": "5",
                "clause_path": ["5", "5.1"],
                "text": "First text",
                "judgement": {"is_relevant": True},
            },
        ]
    )

    assert extracted == [
        {
            "doc_id": "doc-a",
            "spec_no": "23501",
            "clause_id": "5.1",
            "parent_clause_id": "5",
            "clause_path": ["5", "5.1"],
            "texts": ["First text", "Second text"],
        }
    ]


def test_extract_collected_keywords_deduplicates_and_preserves_order() -> None:
    retriever = IterativeLLMRetriever(backend=StubBackend(), evaluator=StubJudge())

    extracted = retriever._extract_collected_keywords(
        [
            {"judgement": {"keywords": ["AMF registration", "ue context"]}},
            {"judgement": {"keywords": ["amf   registration", "security context"]}},
            {"judgement": {"keywords": []}},
        ]
    )

    assert extracted == ["AMF registration", "ue context", "security context"]


def test_iterative_retriever_filters_keywords_from_exclusion_file(tmp_path) -> None:
    exclusion_file = tmp_path / "keyword_exclusions.txt"
    exclusion_file.write_text("UE\nAMF\nControl Plane\n", encoding="utf-8")

    class FilteringJudge(StubJudge):
        def extract_keywords(self, query_text: str, relevant_candidates: list[dict], keyword_limit: int = 5) -> list[dict]:
            del query_text, keyword_limit
            self.keyword_calls.append(("filtering", [str(item["doc_id"]) for item in relevant_candidates]))
            return [
                {
                    "doc_id": item["doc_id"],
                    "keywords": ["UE", "AMF", "registration accept", "Control Plane"],
                    "reason": "keyword match",
                }
                for item in relevant_candidates
            ]

    retriever = IterativeLLMRetriever(
        backend=StubBackend(),
        evaluator=FilteringJudge(),
        keyword_exclusion_path=exclusion_file,
    )

    result = retriever.run("registration", limit=1, iterations=2)

    assert result["iterations"][0]["next_search_terms"] == [
        "registration accept",
        "registration stage2",
        "registration stage3",
        "registration else",
    ]
    assert result["collected_keywords"] == ["registration accept"]
    assert result["all_results"][0]["judgement"]["keywords"] == ["registration accept"]
    assert len(retriever.evaluator.keyword_calls) == 1


def test_iterative_retriever_supports_sentence_style_followups() -> None:
    backend = StubBackend()

    class SentenceJudge(StubJudge):
        def extract_keywords(self, query_text: str, relevant_candidates: list[dict], keyword_limit: int = 5) -> list[dict]:
            del query_text, keyword_limit
            self.keyword_calls.append(("sentence", [str(item["doc_id"]) for item in relevant_candidates]))
            return [
                {
                    "doc_id": item["doc_id"],
                    "keywords": ["Summarize the AMF registration acceptance path"],
                    "reason": "follow-up sentence",
                }
                for item in relevant_candidates
            ]

    judge = SentenceJudge()
    retriever = IterativeLLMRetriever(backend=backend, evaluator=judge)

    result = retriever.run("registration", limit=1, iterations=2)

    assert result["iterations"][0]["next_search_terms"] == [
        "Summarize the AMF registration acceptance path",
        "registration stage2",
        "registration stage3",
        "registration else",
    ]
    assert result["collected_keywords"] == ["Summarize the AMF registration acceptance path"]
    assert judge.keyword_calls == [("sentence", ["registration:stage2", "registration:stage3", "registration:else"])]
