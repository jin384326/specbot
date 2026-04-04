import test from "node:test";
import assert from "node:assert/strict";

import {
  formatErrorMessage,
  isAbortedRequestError,
  mergeSpecbotHits,
  normalizeRequestError,
  resolveWorkApiUrl,
} from "../static/js/utils/work-api.js";

test("resolveWorkApiUrl preserves existing endpoint mappings", () => {
  assert.equal(resolveWorkApiUrl("http://localhost:8010", "/api/clause-browser/specbot/query"), "http://localhost:8010/query");
  assert.equal(resolveWorkApiUrl("http://localhost:8010", "/api/clause-browser/llm-actions"), "http://localhost:8010/llm-actions");
  assert.equal(resolveWorkApiUrl("http://localhost:8010", "/custom"), "/custom");
});

test("formatErrorMessage normalizes nested payloads and validation errors", () => {
  assert.equal(formatErrorMessage("  simple error  "), "simple error");
  assert.equal(formatErrorMessage({ detail: [{ loc: ["body", "query"], msg: "required" }] }), "body.query: required");
  assert.equal(formatErrorMessage('{"detail":{"message":"boom"}}'), "boom");
});

test("mergeSpecbotHits deduplicates by spec/clause and keeps sorted order", () => {
  const merged = mergeSpecbotHits(
    [{ specNo: "23502", clauseId: "4.2.2.2" }],
    [{ specNo: "23501", clauseId: "5.1" }, { specNo: "23502", clauseId: "4.2.2.2" }],
    {
      exclusions: { excludeClauses: [] },
      filterHitsByExclusions(items) {
        return items;
      },
      compareHits(left, right) {
        return `${left.specNo}:${left.clauseId}`.localeCompare(`${right.specNo}:${right.clauseId}`);
      },
    }
  );

  assert.deepEqual(merged, [
    { specNo: "23501", clauseId: "5.1" },
    { specNo: "23502", clauseId: "4.2.2.2" },
  ]);
});

test("normalizeRequestError marks aborted requests with the sentinel error", () => {
  const aborted = normalizeRequestError({ name: "AbortError" });
  assert.equal(isAbortedRequestError(aborted), true);
  assert.equal(isAbortedRequestError(new Error("other")), false);
});
