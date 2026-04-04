import test from "node:test";
import assert from "node:assert/strict";

import {
  createEmptyWorkspaceSnapshot,
  createWorkspaceSnapshot,
  normalizeWorkspacePayload,
} from "../static/js/utils/workspace-state.js";

test("createWorkspaceSnapshot preserves the current serializable workspace fields", () => {
  const state = {
    activeSpecNo: "23501",
    loadedRoots: [{ key: "23501:5" }],
    ui: {
      expandedKeys: new Set(["23501:5"]),
      focusedKey: "23501:5.1",
      viewportKey: "23501:5",
      collapsedSpecs: new Set(["23502"]),
      collapsedLoadedSpecs: new Set(["23501"]),
      clauseQuery: "session",
      specbotQueryText: "PDU session",
      specbotSettings: { limit: 4 },
      boardScope: { releaseData: "2025-12", release: "Rel-18" },
      specbotResults: [{ specNo: "23502", clauseId: "4.2.2.2" }],
      specbotResultsCollapsed: true,
      notes: [{ id: "note-1" }],
      highlights: [{ id: "highlight-1" }],
    },
  };

  assert.deepEqual(createWorkspaceSnapshot(state), {
    activeSpecNo: "23501",
    loadedRoots: [{ key: "23501:5" }],
    expandedKeys: ["23501:5"],
    focusedKey: "23501:5.1",
    viewportKey: "23501:5",
    collapsedSpecs: ["23502"],
    collapsedLoadedSpecs: ["23501"],
    clauseQuery: "session",
    specbotQueryText: "PDU session",
    specbotSettings: { limit: 4 },
    boardScope: { releaseData: "2025-12", release: "Rel-18" },
    specbotResults: [{ specNo: "23502", clauseId: "4.2.2.2" }],
    specbotResultsCollapsed: true,
    notes: [{ id: "note-1" }],
    highlights: [{ id: "highlight-1" }],
  });
});

test("normalizeWorkspacePayload applies the same fallback and normalization rules", () => {
  const calls = [];
  const normalized = normalizeWorkspacePayload(
    {
      activeSpecNo: "23501",
      loadedRoots: [{ key: "raw" }],
      expandedKeys: ["23501:5"],
      focusedKey: "23501:5.1",
      viewportKey: "23501:5",
      collapsedSpecs: ["23502"],
      collapsedLoadedSpecs: ["23501"],
      clauseQuery: "query",
      specbotQueryText: "specbot",
      specbotResultsCollapsed: 1,
      notes: [{ id: "note-1" }],
      highlights: [{ id: "highlight-1" }],
      specbotResults: [
        { specNo: "23502", clauseId: "4.2.2.2" },
        { specNo: "23501", clauseId: "5.1" },
      ],
      boardScope: { releaseData: " 2025-12 ", release: " Rel-18 " },
      specbotSettings: { rejectedClauses: [{ specNo: "23501", clauseId: "5.1" }, { specNo: "23501", clauseId: "5.1" }] },
    },
    {
      ensureForestStableBlockIds(value) {
        calls.push(["ensureForestStableBlockIds", value]);
        return [{ key: "normalized" }];
      },
      normalizeRejectedClauses(value) {
        calls.push(["normalizeRejectedClauses", value]);
        return [{ specNo: "23501", clauseId: "5.1" }];
      },
      sortSpecbotHits(value) {
        calls.push(["sortSpecbotHits", value]);
        return [...value].reverse();
      },
    }
  );

  assert.equal(calls.length, 3);
  assert.deepEqual(normalized, {
    activeSpecNo: "23501",
    loadedRoots: [{ key: "normalized" }],
    expandedKeys: new Set(["23501:5"]),
    focusedKey: "23501:5.1",
    viewportKey: "23501:5",
    collapsedSpecs: new Set(["23502"]),
    collapsedLoadedSpecs: new Set(["23501"]),
    clauseQuery: "query",
    specbotQueryText: "specbot",
    specbotResultsCollapsed: true,
    notes: [{ id: "note-1" }],
    highlights: [{ id: "highlight-1" }],
    specbotResults: [
      { specNo: "23501", clauseId: "5.1" },
      { specNo: "23502", clauseId: "4.2.2.2" },
    ],
    boardScope: { releaseData: "2025-12", release: "Rel-18" },
    specbotSettings: { rejectedClauses: [{ specNo: "23501", clauseId: "5.1" }] },
  });
});

test("createEmptyWorkspaceSnapshot resets runtime fields but preserves caller-owned settings", () => {
  assert.deepEqual(
    createEmptyWorkspaceSnapshot({
      specbotSettings: { limit: 4 },
      boardScope: { releaseData: "2025-12", release: "Rel-18" },
    }),
    {
      activeSpecNo: "",
      loadedRoots: [],
      expandedKeys: [],
      focusedKey: "",
      viewportKey: "",
      collapsedSpecs: [],
      collapsedLoadedSpecs: [],
      clauseQuery: "",
      specbotQueryText: "",
      specbotResultsCollapsed: false,
      notes: [],
      highlights: [],
      specbotResults: [],
      specbotSettings: { limit: 4 },
      boardScope: { releaseData: "2025-12", release: "Rel-18" },
    }
  );
});
