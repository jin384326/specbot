from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator

from embedding.config import DEFAULT_EMBEDDING_DEVICE, DEFAULT_EMBEDDING_MODEL
from embedding.registry import create_embedding_provider
from enrich.enrich_metadata import iter_jsonl


def iter_sliced_records(
    input_path: str,
    offset: int = 0,
    limit: int | None = None,
) -> Iterator:
    emitted = 0
    for index, record in enumerate(iter_jsonl(input_path)):
        if index < offset:
            continue
        if limit is not None and emitted >= limit:
            break
        emitted += 1
        yield record


def build_embeddings(
    input_path: str,
    output_path: str,
    model_name: str = DEFAULT_EMBEDDING_MODEL,
    local_dir: str | None = None,
    output_dim: int | None = None,
    device: str = DEFAULT_EMBEDDING_DEVICE,
    load_in_4bit: bool = True,
    batch_size: int = 4,
    offset: int = 0,
    limit: int | None = None,
    max_length: int = 2048,
    append: bool = False,
) -> int:
    provider = create_embedding_provider(
        model_name,
        local_dir=local_dir,
        output_dim=output_dim,
        device=device,
        load_in_4bit=load_in_4bit,
        max_length=max_length,
    )
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    batch_records = []
    mode = "a" if append else "w"
    with output.open(mode, encoding="utf-8") as handle:
        for record in iter_sliced_records(input_path, offset=offset, limit=limit):
            batch_records.append(record)
            if len(batch_records) < batch_size:
                continue
            batch_vectors = provider.embed_texts([record.embedding_text or record.text for record in batch_records])
            for record, vector in zip(batch_records, batch_vectors):
                record.embedding_model = provider.model_name
                record.embedding_dim = provider.dimension
                record.dense_vector = vector
                handle.write(json.dumps(record.to_dict(), ensure_ascii=True) + "\n")
                count += 1
            batch_records = []
        if batch_records:
            batch_vectors = provider.embed_texts([record.embedding_text or record.text for record in batch_records])
            for record, vector in zip(batch_records, batch_vectors):
                record.embedding_model = provider.model_name
                record.embedding_dim = provider.dimension
                record.dense_vector = vector
                handle.write(json.dumps(record.to_dict(), ensure_ascii=True) + "\n")
                count += 1
    return count
