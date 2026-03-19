Seed judgments for hybrid/BM25 relevance comparison live in [judgments_seed.jsonl](/home/jin3843/codex_project/eval/judgments_seed.jsonl).

Format:
```json
{"query":"SSC mode selection for PDU session","relevant_doc_ids":["23501:clause:5.6.9.3"],"relevant_specs":["23501"]}
```

Current coverage:
- `TS 23.501`
- `TS 23.502`
- `TS 29.502`
- `TS 29.503`
- `TS 38.413`

Run a single comparison:
```bash
python3 tools/eval_hybrid.py \
  --judgments eval/judgments_seed.jsonl \
  --base-url http://localhost:8080 \
  --embed-model qwen3-embedding-8b \
  --local-model-dir /home/jin3843/codex_project/models/Qwen3-Embedding-8B \
  --output-dim 1024 \
  --device cuda \
  --max-length 4096 \
  --sweep \
    bm25:1.0:0.0 \
    anchor_boost:1.0:0.0 \
    hybrid:1.0:0.3 \
    hybrid:1.0:0.8 \
    hybrid:1.0:1.5 \
    hybrid:0.7:2.0
```

Recommended next step:
- Copy this file to a working set such as `eval/judgments_local.jsonl`.
- Add 20-50 more queries from your main use cases.
- Keep both `relevant_doc_ids` and `relevant_specs` where possible so document-level and spec-level metrics can be compared together.
