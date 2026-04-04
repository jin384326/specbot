import test from "node:test";
import assert from "node:assert/strict";

import {
  buildSpecbotExclusions,
  collectLoadedClausePairs,
  dedupeClausePairs,
  filterSpecbotHitsByExclusions,
  getIterationsForDepth,
  getNormalizedRejectedClauses,
  getSpecbotDepthFromSettings,
  parseSpecbotExcludeClauses,
  parseSpecbotExcludeSpecs,
} from "../static/js/utils/specbot-state.js";

test("collectLoadedClausePairs traverses the loaded tree recursively", () => {
  assert.deepEqual(
    collectLoadedClausePairs([
      {
        specNo: "23501",
        clauseId: "5",
        children: [{ specNo: "23501", clauseId: "5.1", children: [] }],
      },
    ]),
    [
      { specNo: "23501", clauseId: "5" },
      { specNo: "23501", clauseId: "5.1" },
    ]
  );
});

test("specbot exclusion parsers preserve only valid trimmed values", () => {
  assert.deepEqual(parseSpecbotExcludeSpecs(" 23501,\n\n23502 "), ["23501", "23502"]);
  assert.deepEqual(parseSpecbotExcludeClauses("23501:5.1, invalid, 23502:4.2.2.2"), [
    { specNo: "23501", clauseId: "5.1" },
    { specNo: "23502", clauseId: "4.2.2.2" },
  ]);
});

test("dedupeClausePairs and rejected clause normalization keep unique valid pairs", () => {
  const items = [{ specNo: "23501", clauseId: "5.1" }, { specNo: "23501", clauseId: "5.1" }, { specNo: "", clauseId: "x" }];
  assert.deepEqual(dedupeClausePairs(items), [{ specNo: "23501", clauseId: "5.1" }]);
  assert.deepEqual(getNormalizedRejectedClauses(items), [{ specNo: "23501", clauseId: "5.1" }]);
});

test("buildSpecbotExclusions combines manual, rejected, loaded, and document inclusion rules", () => {
  const exclusions = buildSpecbotExclusions({
    settings: {
      includedSpecs: ["23501"],
      excludeSpecs: ["29512"],
      excludeClauses: [{ specNo: "23501", clauseId: "5.1" }],
    },
    documents: [{ specNo: "23501" }, { specNo: "23502" }],
    loadedRoots: [{ specNo: "23503", clauseId: "1", children: [] }],
    rejectedClauses: [{ specNo: "23504", clauseId: "2" }],
    compareMixedToken: (left, right) => String(left).localeCompare(String(right)),
    compareSpecbotHits: (left, right) => `${left.specNo}:${left.clauseId}`.localeCompare(`${right.specNo}:${right.clauseId}`),
  });

  assert.deepEqual(exclusions, {
    excludeSpecs: ["23502", "29512"],
    excludeClauses: [
      { specNo: "23501", clauseId: "5.1" },
      { specNo: "23503", clauseId: "1" },
      { specNo: "23504", clauseId: "2" },
    ],
  });
});

test("filterSpecbotHitsByExclusions removes excluded specs and exact clause pairs", () => {
  assert.deepEqual(
    filterSpecbotHitsByExclusions(
      [
        { specNo: "23501", clauseId: "5.1" },
        { specNo: "23502", clauseId: "4.2.2.2" },
        { specNo: "29512", clauseId: "7.1" },
      ],
      {
        excludeSpecs: ["29512"],
        excludeClauses: [{ specNo: "23501", clauseId: "5.1" }],
      }
    ),
    [{ specNo: "23502", clauseId: "4.2.2.2" }]
  );
});

test("depth helpers preserve existing query depth mapping", () => {
  assert.equal(getIterationsForDepth("short"), 0);
  assert.equal(getIterationsForDepth("medium"), 1);
  assert.equal(getIterationsForDepth("long"), 2);
  assert.equal(getSpecbotDepthFromSettings({ queryDepth: "long" }), "long");
  assert.equal(getSpecbotDepthFromSettings({ iterations: 0 }), "short");
  assert.equal(getSpecbotDepthFromSettings({ iterations: 1 }), "medium");
  assert.equal(getSpecbotDepthFromSettings({ iterations: 2 }), "long");
});
