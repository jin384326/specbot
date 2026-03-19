from __future__ import annotations

import re

GENERIC_ANCHORS = {
    "general",
    "overview",
    "message",
    "messages",
    "procedure",
    "procedures",
    "information element",
    "ie",
}


def normalize_anchor(anchor: str) -> str:
    normalized = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", anchor or "")
    normalized = re.sub(r"[_/]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def is_noisy_anchor(anchor: str) -> bool:
    lowered = normalize_anchor(anchor).lower()
    return not lowered or lowered in GENERIC_ANCHORS
