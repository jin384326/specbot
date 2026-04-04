import test from "node:test";
import assert from "node:assert/strict";

import {
  buildRejectedSpecbotClausesHtml,
  buildSpecbotDocumentSettingsHtml,
  buildSpecbotResultsHtml,
  getSpecbotDocumentSelectionCount,
  getSpecbotQueryLoadingLabel,
  normalizeSpecbotDepth,
} from "../static/js/utils/specbot-ui.js";

const escapeHtml = (value) => String(value).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");

test("specbot result html includes actions and fallback empty state", () => {
  assert.match(buildSpecbotResultsHtml([], escapeHtml), /SpecBot/);
  const html = buildSpecbotResultsHtml([{ specNo: "23501", clauseId: "5.1", clausePath: ["5", "5.1"], textPreview: "preview" }], escapeHtml);
  assert.match(html, /data-action="load-specbot-hit"/);
  assert.match(html, /23501/);
});

test("specbot settings html helpers preserve checkbox and rejected-clause markup", () => {
  const docsHtml = buildSpecbotDocumentSettingsHtml([{ specNo: "23501", specTitle: "Title" }], new Set(["23501"]), escapeHtml);
  assert.match(docsHtml, /checked/);
  const rejectedHtml = buildRejectedSpecbotClausesHtml([{ specNo: "23501", clauseId: "5.1" }], escapeHtml);
  assert.match(rejectedHtml, /data-action="remove-rejected-clause"/);
});

test("specbot ui labels preserve current text mapping", () => {
  assert.equal(getSpecbotDocumentSelectionCount(2, 5), "2 / 5 selected");
  assert.equal(getSpecbotQueryLoadingLabel("queued"), "대기 중");
  assert.equal(getSpecbotQueryLoadingLabel("started"), "실행 중");
  assert.equal(getSpecbotQueryLoadingLabel("other"), "수행 중");
  assert.equal(normalizeSpecbotDepth("short"), "short");
  assert.equal(normalizeSpecbotDepth("medium"), "medium");
  assert.equal(normalizeSpecbotDepth("x"), "medium");
});
