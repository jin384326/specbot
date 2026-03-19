from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from embedding.build_embeddings import build_embeddings
from embedding.registry import create_embedding_provider


def test_hash_embedding_provider_is_deterministic() -> None:
    provider = create_embedding_provider("hash-16")
    vectors = provider.embed_texts(["PDU Session handling", "PDU Session handling"])
    assert len(vectors[0]) == 16
    assert vectors[0] == vectors[1]


def test_registry_supports_qwen_provider_without_loading_model() -> None:
    with patch("embedding.registry.QwenEmbeddingProvider") as provider_cls:
        provider_cls.return_value.model_name = "Qwen/Qwen3-Embedding-0.6B"
        provider = create_embedding_provider("qwen3-embedding-0.6b", local_dir="/tmp/fake", output_dim=1024, device="cpu")
        assert provider.model_name == "Qwen/Qwen3-Embedding-0.6B"


def test_build_embeddings_writes_dense_vectors(tmp_path: Path) -> None:
    source = tmp_path / "enriched.jsonl"
    record = {
        "doc_id": "23501:clause:1",
        "doc_type": "clause_doc",
        "content_kind": "clause",
        "spec_no": "23501",
        "text": "Scope text",
        "embedding_text": "System architecture scope",
    }
    source.write_text(json.dumps(record) + "\n", encoding="utf-8")
    output = tmp_path / "embedded.jsonl"
    count = build_embeddings(str(source), str(output), model_name="hash-16")
    assert count == 1
    payload = json.loads(output.read_text(encoding="utf-8").strip())
    assert payload["embedding_model"] == "hash-16"
    assert payload["embedding_dim"] == 16
    assert len(payload["dense_vector"]) == 16


def test_build_embeddings_supports_offset_limit_and_append(tmp_path: Path) -> None:
    source = tmp_path / "enriched.jsonl"
    lines = [
        {
            "doc_id": f"23501:clause:{idx}",
            "doc_type": "clause_doc",
            "content_kind": "clause",
            "spec_no": "23501",
            "text": f"Scope text {idx}",
            "embedding_text": f"System architecture scope {idx}",
        }
        for idx in range(3)
    ]
    source.write_text("\n".join(json.dumps(item) for item in lines) + "\n", encoding="utf-8")
    output = tmp_path / "embedded.jsonl"

    first_count = build_embeddings(str(source), str(output), model_name="hash-16", limit=1)
    second_count = build_embeddings(str(source), str(output), model_name="hash-16", offset=1, limit=2, append=True)

    assert first_count == 1
    assert second_count == 2
    payload = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert [item["doc_id"] for item in payload] == [
        "23501:clause:0",
        "23501:clause:1",
        "23501:clause:2",
    ]
