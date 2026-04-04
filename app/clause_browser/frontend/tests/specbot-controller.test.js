import test from "node:test";
import assert from "node:assert/strict";

import { createSpecbotController } from "../static/js/controllers/specbot-controller.js";

function createClassList() {
  const classes = new Set(["hidden"]);
  return {
    add(name) {
      classes.add(name);
    },
    remove(name) {
      classes.delete(name);
    },
    toggle(name, force) {
      if (force === undefined) {
        if (classes.has(name)) {
          classes.delete(name);
          return false;
        }
        classes.add(name);
        return true;
      }
      if (force) {
        classes.add(name);
        return true;
      }
      classes.delete(name);
      return false;
    },
    contains(name) {
      return classes.has(name);
    },
  };
}

function createControllerFixture() {
  const events = {
    persisted: 0,
    messages: [],
  };
  const state = {
    documents: [{ specNo: "100" }, { specNo: "200" }],
    loadedRoots: [{ specNo: "100", clauseId: "1.1" }],
    ui: {
      specbotSettings: {
        rejectedClauses: [{ specNo: "200", clauseId: "3.1" }],
      },
      specbotResults: [
        { specNo: "200", clauseId: "9.1" },
        { specNo: "100", clauseId: "1.1" },
      ],
      specbotResultsCollapsed: false,
      specbotQueryStatus: "",
      specbotDocumentSettingsLoading: false,
      isSpecbotSettingsOpen: false,
    },
  };
  const checkbox100 = { checked: true, value: "100" };
  const checkbox200 = { checked: false, value: "200" };
  const elements = {
    specbotSettingsModal: {
      classList: createClassList(),
      attrs: {},
      setAttribute(name, value) {
        this.attrs[name] = value;
      },
    },
    specbotResultList: {
      classList: createClassList(),
      attrs: {},
      innerHTML: "",
      setAttribute(name, value) {
        this.attrs[name] = value;
      },
      querySelectorAll() {
        return [];
      },
    },
    toggleSpecbotResults: {
      textContent: "",
      title: "",
      attrs: {},
      setAttribute(name, value) {
        this.attrs[name] = value;
      },
    },
    settingDocumentList: {
      innerHTML: "",
      querySelectorAll(selector) {
        if (selector === "[data-action='toggle-specbot-doc']") {
          return [checkbox100, checkbox200];
        }
        if (selector === "[data-action='toggle-specbot-doc']:checked") {
          return [checkbox100].filter((item) => item.checked);
        }
        return [];
      },
    },
    settingDocumentSelectionCount: { textContent: "" },
    settingRejectedClauseList: {
      innerHTML: "",
      querySelectorAll() {
        return [];
      },
    },
    settingClearRejectedClauses: { disabled: false },
    specbotQuery: { disabled: false, value: "query" },
    specbotSpinner: { classList: createClassList() },
    runSpecbotLabel: { textContent: "" },
    specbotQueryStatus: { classList: createClassList() },
    settingBaseUrl: { value: " https://api.example.com " },
    settingConfigBaseUrl: { value: " https://config.example.com " },
    settingLimit: { value: "4" },
    settingIterations: { value: "1" },
    settingNextIterationLimit: { value: "2" },
    settingFollowupMode: { value: "sentence-summary" },
    settingSummary: { value: "short" },
    settingRegistry: { value: " registry-a " },
    settingLocalModelDir: { value: " /tmp/model " },
    settingDevice: { value: " cuda " },
    settingSparseBoost: { value: "0" },
    settingVectorBoost: { value: "1" },
    settingExcludeSpecs: { value: "300\n400" },
    settingExcludeClauses: { value: "500:6.1" },
    specbotDepthOptions: [
      { value: "short", checked: false },
      { value: "medium", checked: true },
      { value: "long", checked: false },
    ],
  };

  const controller = createSpecbotController({
    state,
    elements,
    dedupeClausePairs: (items) =>
      items.filter(
        (item, index, array) =>
          array.findIndex((candidate) => candidate.specNo === item.specNo && candidate.clauseId === item.clauseId) === index
      ),
    getNormalizedRejectedClauses: (items) => Array.isArray(items) ? items.map((item) => ({ specNo: String(item.specNo), clauseId: String(item.clauseId) })) : [],
    getIterationsForDepth: (depth) => ({ short: 0, medium: 1, long: 2 }[depth] ?? 1),
    getSpecbotDepthFromSettings: (settings) => settings.queryDepth || "medium",
    parseSpecbotExcludeSpecs: (value) => String(value).split(/\n+/).map((item) => item.trim()).filter(Boolean),
    parseSpecbotExcludeClauses: (value) =>
      String(value)
        .split(/\n+/)
        .map((item) => item.trim())
        .filter(Boolean)
        .map((item) => {
          const [specNo, clauseId] = item.split(":");
          return { specNo, clauseId };
        }),
    normalizeSpecbotDepth: (value) => (value === "short" || value === "long" ? value : "medium"),
    buildSpecbotExclusionsFromState: () => ({ excludeSpecs: ["300", "400"], excludeClauses: [{ specNo: "500", clauseId: "6.1" }] }),
    filterSpecbotHitsByExclusionsFromState: (hits, exclusions) =>
      hits.filter(
        (item) =>
          !exclusions.excludeSpecs.includes(item.specNo) &&
          !exclusions.excludeClauses.some((candidate) => candidate.specNo === item.specNo && candidate.clauseId === item.clauseId)
      ),
    buildSpecbotResultsHtml: () => "<div>results</div>",
    buildSpecbotDocumentSettingsHtml: () => "<div>docs</div>",
    buildRejectedSpecbotClausesHtml: () => "<div>rejected</div>",
    getSpecbotDocumentSelectionCount: (selected, total) => `${selected}/${total}`,
    getSpecbotQueryLoadingLabel: () => "loading",
    compareSpecbotHits: (left, right) => `${left.specNo}:${left.clauseId}`.localeCompare(`${right.specNo}:${right.clauseId}`),
    compareMixedToken: (left, right) => String(left).localeCompare(String(right)),
    escapeHtml: (value) => String(value),
    persistSessionState: () => {
      events.persisted += 1;
    },
    setMessage: (text, isError) => {
      events.messages.push({ text, isError });
    },
    beginBusy: () => true,
    endBusy: () => {},
    getBoardScope: () => ({ releaseData: "", release: "" }),
    streamSpecbotQuery: async () => ({ hits: [] }),
    isAbortedRequestError: () => false,
    loadClauseFromSpec: async () => {},
    renderLoadedTree: () => {},
  });

  return { controller, state, elements, events };
}

test("specbot controller toggles result panel without changing render contract", () => {
  const { controller, state, elements, events } = createControllerFixture();

  controller.toggleSpecbotResultsPanel();

  assert.equal(state.ui.specbotResultsCollapsed, true);
  assert.equal(elements.toggleSpecbotResults.textContent, "+");
  assert.equal(elements.specbotResultList.attrs["aria-hidden"], "true");
  assert.equal(events.persisted, 1);
});

test("specbot controller saves settings and prunes current results", () => {
  const { controller, state, elements, events } = createControllerFixture();

  controller.saveSpecbotSettings();

  assert.deepEqual(state.ui.specbotSettings.includedSpecs, ["100"]);
  assert.deepEqual(state.ui.specbotSettings.excludeSpecs, ["300", "400"]);
  assert.deepEqual(state.ui.specbotSettings.excludeClauses, [{ specNo: "500", clauseId: "6.1" }]);
  assert.deepEqual(state.ui.specbotSettings.rejectedClauses, [{ specNo: "200", clauseId: "3.1" }]);
  assert.equal(state.ui.specbotSettings.queryDepth, "medium");
  assert.equal(state.ui.specbotSettings.iterations, 1);
  assert.equal(state.ui.isSpecbotSettingsOpen, false);
  assert.equal(elements.specbotSettingsModal.classList.contains("hidden"), true);
  assert.deepEqual(state.ui.specbotResults, [
    { specNo: "100", clauseId: "1.1" },
    { specNo: "200", clauseId: "9.1" },
  ]);
  assert.ok(events.persisted >= 1);
});
