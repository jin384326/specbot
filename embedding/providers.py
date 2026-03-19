from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Protocol

from embedding.config import DEFAULT_QUERY_PROMPT


class EmbeddingProvider(Protocol):
    model_name: str
    dimension: int

    def embed_texts(self, texts: list[str], prompt_name: str | None = None) -> list[list[float]]:
        ...


@dataclass
class HashEmbeddingProvider:
    model_name: str = "hash-16"
    dimension: int = 16

    def embed_texts(self, texts: list[str], prompt_name: str | None = None) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        for token in text.lower().split():
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=16).digest()
            for idx in range(self.dimension):
                value = digest[idx % len(digest)] / 255.0
                vector[idx] += value if idx % 2 == 0 else -value
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [round(value / norm, 6) for value in vector]


class SentenceTransformerProvider:
    def __init__(self, model_name: str) -> None:
        from sentence_transformers import SentenceTransformer  # type: ignore

        self.model_name = model_name
        self._model = SentenceTransformer(model_name)
        self.dimension = int(self._model.get_sentence_embedding_dimension())

    def embed_texts(self, texts: list[str], prompt_name: str | None = None) -> list[list[float]]:
        kwargs = {"normalize_embeddings": True}
        if prompt_name:
            kwargs["prompt_name"] = prompt_name
        embeddings = self._model.encode(texts, **kwargs)
        return [[float(value) for value in row] for row in embeddings]


class QwenEmbeddingProvider:
    def __init__(
        self,
        model_name: str,
        local_dir: str | None = None,
        output_dim: int = 1024,
        device: str = "cuda",
        load_in_4bit: bool = True,
        max_length: int = 2048,
    ) -> None:
        import torch
        from transformers import AutoModel, AutoTokenizer, BitsAndBytesConfig

        self.model_name = model_name
        self.dimension = output_dim
        self.max_length = max_length
        model_ref = local_dir or model_name
        self._torch = torch
        self._tokenizer = AutoTokenizer.from_pretrained(model_ref, trust_remote_code=True)

        model_kwargs: dict = {
            "trust_remote_code": True,
            "device_map": device if device != "cpu" else None,
            "dtype": torch.bfloat16 if device.startswith("cuda") else torch.float32,
        }
        if load_in_4bit and device.startswith("cuda"):
            model_kwargs["quantization_config"] = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=torch.bfloat16,
            )
            model_kwargs["device_map"] = "auto"
        self._model = AutoModel.from_pretrained(model_ref, **model_kwargs).eval()

    def embed_texts(self, texts: list[str], prompt_name: str | None = None) -> list[list[float]]:
        prompt_prefix = DEFAULT_QUERY_PROMPT if prompt_name == "query" else ""
        prepared_texts = [prompt_prefix + text if prompt_prefix else text for text in texts]
        batched = self._tokenizer(
            prepared_texts,
            padding=True,
            truncation=True,
            max_length=self.max_length,
            return_tensors="pt",
        )
        device = next(self._model.parameters()).device
        batched = {key: value.to(device) for key, value in batched.items()}
        with self._torch.no_grad():
            outputs = self._model(**batched)
            hidden = outputs.last_hidden_state
            attention_mask = batched["attention_mask"]
            vectors = self._last_token_pool(hidden, attention_mask)
            vectors = vectors[:, : self.dimension]
            vectors = self._torch.nn.functional.normalize(vectors, p=2, dim=1)
        return [[float(value) for value in row] for row in vectors.detach().cpu()]

    def _last_token_pool(self, hidden_states, attention_mask):
        left_padding = attention_mask[:, -1].sum() == attention_mask.shape[0]
        if left_padding:
            return hidden_states[:, -1]
        sequence_lengths = attention_mask.sum(dim=1) - 1
        batch_size = hidden_states.shape[0]
        return hidden_states[self._torch.arange(batch_size, device=hidden_states.device), sequence_lengths]
