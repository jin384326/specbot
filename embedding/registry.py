from __future__ import annotations

from embedding.config import DEFAULT_EMBEDDING_MODEL, get_embedding_model_config
from embedding.providers import (
    EmbeddingProvider,
    HashEmbeddingProvider,
    QwenEmbeddingProvider,
    SentenceTransformerProvider,
)


def create_embedding_provider(
    model_name: str = DEFAULT_EMBEDDING_MODEL,
    local_dir: str | None = None,
    output_dim: int | None = None,
    device: str = "cpu",
    load_in_4bit: bool = True,
    max_length: int = 2048,
) -> EmbeddingProvider:
    normalized = model_name.strip().lower()
    if normalized.startswith("sentence-transformers:"):
        actual_name = model_name.split(":", 1)[1]
        return SentenceTransformerProvider(actual_name)
    config = get_embedding_model_config(model_name)
    if config.alias == "hash-16":
        return HashEmbeddingProvider(model_name="hash-16", dimension=16)
    if config.model_name.startswith("Qwen/"):
        return QwenEmbeddingProvider(
            model_name=config.model_name,
            local_dir=local_dir or config.default_local_dir,
            output_dim=output_dim or config.default_dimension,
            device=device,
            load_in_4bit=load_in_4bit,
            max_length=max_length,
        )
    raise ValueError(f"Unsupported embedding model: {model_name}")
