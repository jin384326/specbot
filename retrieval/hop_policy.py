from __future__ import annotations

from parser.models import DocRecord

STAGE_BUCKET_ORDER = ["Stage 2", "Stage 3", "else"]


def infer_hop_stage_targets(records: list[DocRecord]) -> list[str]:
    targets: list[str] = []
    for record in records:
        if record.stage_hint and record.stage_hint not in targets:
            targets.append(record.stage_hint)
    if targets:
        return [stage for stage in STAGE_BUCKET_ORDER if stage in targets]
    return list(STAGE_BUCKET_ORDER)
