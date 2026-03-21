# Vespa Application Package

This directory contains a draft Vespa application package and local tooling for the 3GPP Spec Finder.

Files:
- `schema/spec_finder.sd`: document schema and ranking profiles
- `schema/services.xml`: container/content cluster wiring
- `schema/hosts.xml`: local host alias
- `schema/deployment.xml`: minimal deployment descriptor
- `schema/validation-overrides.xml`: validation override placeholder
- `schema/search/query-profiles/default.xml`: default query profile
- `schema/search/query-profiles/types/root.xml`: query profile type definition
- `docker-compose.yml`: local Vespa container draft

Typical flow:
```bash
docker compose -f vespa/docker-compose.yml up -d
python3 -m app.main build-corpus Specs/2025-12/Rel-18/23501-ic0.docx --output ./artifact/spec_finder_corpus.jsonl --overwrite
python3 -m app.main enrich-corpus --input /tmp/spec_finder_corpus.jsonl --output /tmp/spec_finder_enriched.jsonl
python3 -m app.main export-vespa --input /tmp/spec_finder_enriched.jsonl --output /tmp/spec_finder_vespa.jsonl
python3 -m app.main package-vespa-app --app-dir vespa/schema --output /tmp/spec_finder_app.zip
python3 -m app.main deploy-vespa-http --app-dir vespa/schema --base-url http://localhost:8080 --config-base-url http://localhost:19071
python3 -m app.main preview-vespa-query --query "SSC mode in TS 23.501 stage 2"
python3 -m app.main feed-vespa-http --input /tmp/spec_finder_vespa.jsonl --base-url http://localhost:8080
python3 -m app.main query-vespa-http --query "SSC mode in TS 23.501 stage 2" --base-url http://localhost:8080 --ranking anchor_boost
python3 -m app.main smoke-test-vespa-http --query "SSC mode in TS 23.501 stage 2" --base-url http://localhost:8080
```

Notes:
- `table_raw` is exported as `table_raw_json` for Vespa compatibility.
- Feed is sequential but batched at the file-reader level and includes retry/failure accounting.
- Deployment uploads a zipped application package to Vespa config server `prepareandactivate`.
- The compose file uses the image default startup path; deploy the application package after the container becomes reachable.
- Ranking profiles are starter profiles only and should be tuned on real judgments.
