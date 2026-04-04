import test from "node:test";
import assert from "node:assert/strict";

import { createSelectionNoteController } from "../static/js/controllers/selection-note-controller.js";

function createClassList() {
  const classes = new Set();
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
      } else {
        classes.delete(name);
      }
      return force;
    },
    contains(name) {
      return classes.has(name);
    },
  };
}

function createFixture(overrides = {}) {
  const state = overrides.state || {
    ui: {
      notes: [],
      highlights: [],
      openSelectionNoteIds: new Set(),
      selectionNoteOverlayPositions: {},
      selectionSnapshot: null,
      clauseNoteModalKey: "",
    },
  };
  const calls = {
    persisted: 0,
    rerenderLoadedNodes: [],
    rerenderLoadedNode: [],
    renderLoadedTree: 0,
    messages: [],
    ensureSelectionMutationAllowed: [],
    ...overrides.calls,
  };
  const elements = overrides.elements || {
    selectionNotePanel: {
      innerHTML: "",
      classList: createClassList(),
      attrs: {},
      setAttribute(name, value) {
        this.attrs[name] = value;
      },
    },
    selectionNoteOverlay: {
      innerHTML: "",
      classList: createClassList(),
      attrs: {},
      setAttribute(name, value) {
        this.attrs[name] = value;
      },
      querySelectorAll() {
        return [];
      },
    },
    clauseNoteModal: {
      classList: createClassList(),
      attrs: {},
      setAttribute(name, value) {
        this.attrs[name] = value;
      },
    },
  };

  const controller = createSelectionNoteController({
    state,
    elements,
    getSelectionNoteIndex: () => ({}),
    getSelectionNotesForClauseFromIndex: () => [],
    getSelectionNotesForTarget: (clauseKey, blockIndex) =>
      (state.ui.notes || []).filter((note) => note.clauseKey === clauseKey && note.blockIndex === blockIndex),
    getResolvedBlockIndexForReference: (_clauseKey, blockIndex) => Number(blockIndex ?? -1),
    getBlockIdByIndex: () => "block-1",
    getCurrentSelectionTargets: () => [{ clauseKey: "23501:1.1", clauseLabel: "23501 / 1.1", blockId: "block-1", blockIndex: 0, rowIndex: -1, cellIndex: -1, cellId: "", rowText: "Selected row" }],
    getEffectiveSelection: () => ({ hasSelection: true, text: "Selected text" }),
    getLabelForKey: (key) => key,
    createHighlightEntry: ({ clauseKey, blockId, blockIndex, rowIndex, cellIndex, cellId, rowText }) => ({
      id: [clauseKey, blockId, blockIndex, rowIndex, cellIndex, cellId, rowText].join(":"),
      clauseKey,
      blockId,
      blockIndex,
      rowIndex,
      cellIndex,
      cellId,
      rowText,
    }),
    ensureHighlightEntry: (entry) => {
      if (!(state.ui.highlights || []).some((item) => item.id === entry.id)) {
        state.ui.highlights = [entry, ...(state.ui.highlights || [])];
      }
    },
    getAffectedClauseKeysForSelectionArtifacts: (items) => [...new Set(items.map((item) => item.clauseKey).filter(Boolean))],
    persistSessionState: () => {
      calls.persisted += 1;
    },
    rerenderLoadedNodes: (keys) => {
      calls.rerenderLoadedNodes.push(keys);
    },
    rerenderLoadedNode: (key) => {
      calls.rerenderLoadedNode.push(key);
    },
    renderLoadedTree: () => {
      calls.renderLoadedTree += 1;
    },
    requestSelectionSidebarRender: () => {},
    focusNode: () => {},
    setMessage: (text, isError) => {
      calls.messages.push({ text, isError });
    },
    ensureSelectionMutationAllowed: async (actionLabel, options) => {
      calls.ensureSelectionMutationAllowed.push({ actionLabel, options });
      if (typeof overrides.ensureSelectionMutationAllowed === "function") {
        return overrides.ensureSelectionMutationAllowed(actionLabel, options);
      }
      return true;
    },
    syncNoteReadOnlyOnOpen: overrides.syncNoteReadOnlyOnOpen || (async () => false),
    isNoteReadOnly: overrides.isNoteReadOnly || (() => false),
    markNoteDirty: overrides.markNoteDirty || (() => {}),
    clearNoteDirty: overrides.clearNoteDirty || (() => {}),
    hasDirtyNote: overrides.hasDirtyNote || (() => false),
    inferSourceLanguage: () => "en",
    escapeHtml: (value) => String(value),
    escapeKey: (value) => String(value),
    escapeSelector: (value) => String(value),
    expandNodePath: () => {},
  });

  return { controller, state, elements, calls };
}

test("selection note controller adds manual note and linked highlight", async () => {
  const { controller, state, calls } = createFixture();

  await controller.addManualSelectionNote();

  assert.equal(state.ui.notes.length, 1);
  assert.equal(state.ui.notes[0].type, "selection");
  assert.equal(state.ui.notes[0].sourceText, "Selected text");
  assert.equal(state.ui.highlights.length, 1);
  assert.equal(state.ui.openSelectionNoteIds.size, 1);
  assert.equal(calls.persisted, 1);
  assert.deepEqual(calls.rerenderLoadedNodes[0], ["23501:1.1"]);
  assert.deepEqual(calls.ensureSelectionMutationAllowed, [{ actionLabel: "선택 메모를 추가", options: undefined }]);
});

test("selection note controller blocks manual note when selection mutation is not allowed", async () => {
  const { controller, state, calls } = createFixture({
    ensureSelectionMutationAllowed: async () => false,
  });

  await controller.addManualSelectionNote();

  assert.equal(state.ui.notes.length, 0);
  assert.equal(state.ui.highlights.length, 0);
  assert.equal(calls.persisted, 0);
});

test("selection note overlay renders readonly mode without delete action", () => {
  const { controller, state, elements } = createFixture({
    isNoteReadOnly: () => true,
  });
  state.ui.notes = [{
    id: "note-1",
    type: "selection",
    clauseKey: "23501:1.1",
    blockId: "block-1",
    blockIndex: 0,
    rowIndex: -1,
    cellIndex: -1,
    cellId: "",
    clauseLabel: "23501 / 1.1",
    translation: "memo text",
  }];
  state.ui.openSelectionNoteIds = new Set(["note-1"]);
  state.ui.selectionNoteOverlayPositions = { "note-1": { top: 10, left: 20, width: 320 } };
  const previousDocument = globalThis.document;
  const previousHTMLElement = globalThis.HTMLElement;
  globalThis.document = {
    getElementById() {
      return null;
    },
    querySelector() {
      return null;
    },
    querySelectorAll() {
      return [];
    },
  };
  globalThis.HTMLElement = class HTMLElementMock {};
  try {
    controller.renderSelectionSidebar();

    assert.match(elements.selectionNoteOverlay.innerHTML, /조회 전용으로만 볼 수 있습니다/);
    assert.match(elements.selectionNoteOverlay.innerHTML, /readonly/);
    assert.doesNotMatch(elements.selectionNoteOverlay.innerHTML, /data-action="delete-note"/);
  } finally {
    globalThis.document = previousDocument;
    globalThis.HTMLElement = previousHTMLElement;
  }
});

test("selection note close warns once and still closes when dirty note becomes locked", async () => {
  const dirtyIds = new Set(["note-1"]);
  const clearedIds = [];
  const { controller, state, calls } = createFixture({
    ensureSelectionMutationAllowed: async () => false,
    hasDirtyNote: (noteId) => dirtyIds.has(String(noteId || "")),
    clearNoteDirty: (noteId) => {
      clearedIds.push(noteId);
      dirtyIds.delete(String(noteId || ""));
    },
  });
  state.ui.notes = [{
    id: "note-1",
    type: "selection",
    clauseKey: "23501:1.1",
    blockId: "block-1",
    blockIndex: 0,
  }];
  state.ui.openSelectionNoteIds = new Set(["note-1"]);
  const previousDocument = globalThis.document;
  globalThis.document = {
    querySelectorAll() {
      return [];
    },
  };
  try {
    await controller.closeSelectionNoteById("note-1");
  } finally {
    globalThis.document = previousDocument;
  }

  assert.equal(state.ui.openSelectionNoteIds.has("note-1"), false);
  assert.deepEqual(clearedIds, ["note-1"]);
  assert.deepEqual(calls.ensureSelectionMutationAllowed, [{
    actionLabel: "메모 변경을 완료",
    options: { warnOnce: true },
  }]);
});

test("selection note controller deletes note and prunes orphan highlight", async () => {
  const { controller, state, calls } = createFixture();
  state.ui.notes = [{
    id: "note-1",
    type: "selection",
    clauseKey: "23501:1.1",
    blockId: "block-1",
    blockIndex: 0,
    rowIndex: -1,
    cellIndex: -1,
    cellId: "",
    rowText: "Selected row",
  }];
  state.ui.highlights = [{
    id: "23501:1.1:block-1:0:-1:-1::Selected row",
    clauseKey: "23501:1.1",
  }];
  state.ui.openSelectionNoteIds = new Set(["note-1"]);
  state.ui.selectionNoteOverlayPositions = { "note-1": { top: 10, left: 20, width: 320 } };

  await controller.deleteNote("note-1");

  assert.deepEqual(state.ui.notes, []);
  assert.deepEqual(state.ui.highlights, []);
  assert.equal(state.ui.openSelectionNoteIds.size, 0);
  assert.deepEqual(state.ui.selectionNoteOverlayPositions, {});
  assert.equal(calls.persisted, 1);
  assert.deepEqual(calls.rerenderLoadedNodes[0], ["23501:1.1"]);
});
