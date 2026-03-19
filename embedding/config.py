from __future__ import annotations

from dataclasses import dataclass


DEFAULT_EMBEDDING_MODEL = "qwen3-embedding-0.6b"
DEFAULT_EMBEDDING_REPO = "Qwen/Qwen3-Embedding-0.6B"
DEFAULT_EMBEDDING_LOCAL_DIR = "models/Qwen3-Embedding-0.6B"
DEFAULT_EMBEDDING_DIMENSION = 1024
DEFAULT_EMBEDDING_DEVICE = "cuda"
DEFAULT_QUERY_PROMPT = "Instruct: Retrieve relevant 3GPP specification units.\nQuery: "


@dataclass(frozen=True)
class EmbeddingModelConfig:
    alias: str
    model_name: str
    default_dimension: int
    default_local_dir: str | None = None
    supports_prompts: bool = False


EMBEDDING_MODEL_CONFIGS = {
    "hash-16": EmbeddingModelConfig(
        alias="hash-16",
        model_name="hash-16",
        default_dimension=16,
    ),
    "qwen3-embedding-0.6b": EmbeddingModelConfig(
        alias="qwen3-embedding-0.6b",
        model_name=DEFAULT_EMBEDDING_REPO,
        default_dimension=DEFAULT_EMBEDDING_DIMENSION,
        default_local_dir=DEFAULT_EMBEDDING_LOCAL_DIR,
        supports_prompts=True,
    ),
    "qwen/qwen3-embedding-0.6b": EmbeddingModelConfig(
        alias="qwen3-embedding-0.6b",
        model_name=DEFAULT_EMBEDDING_REPO,
        default_dimension=DEFAULT_EMBEDDING_DIMENSION,
        default_local_dir=DEFAULT_EMBEDDING_LOCAL_DIR,
        supports_prompts=True,
    ),
    "qwen3-embedding-8b": EmbeddingModelConfig(
        alias="qwen3-embedding-8b",
        model_name="Qwen/Qwen3-Embedding-8B",
        default_dimension=1024,
        default_local_dir="models/Qwen3-Embedding-8B",
        supports_prompts=True,
    ),
    "qwen/qwen3-embedding-8b": EmbeddingModelConfig(
        alias="qwen3-embedding-8b",
        model_name="Qwen/Qwen3-Embedding-8B",
        default_dimension=1024,
        default_local_dir="models/Qwen3-Embedding-8B",
        supports_prompts=True,
    ),
}


def get_embedding_model_config(model_name: str) -> EmbeddingModelConfig:
    normalized = model_name.strip().lower()
    if normalized not in EMBEDDING_MODEL_CONFIGS:
        raise ValueError(f"Unsupported embedding model: {model_name}")
    return EMBEDDING_MODEL_CONFIGS[normalized]
