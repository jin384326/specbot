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

function createFixture() {
  const state = {
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
  };
  const elements = {
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
    ensureSelectionMutationAllowed: async (actionLabel) => {
      calls.ensureSelectionMutationAllowed.push(actionLabel);
      return true;
    },
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
  assert.deepEqual(calls.ensureSelectionMutationAllowed, ["선택 메모를 추가"]);
});

test("selection note controller blocks manual note when selection mutation is not allowed", async () => {
  const { state, calls } = createFixture();
  const controller = createSelectionNoteController({
    state,
    elements: {
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
    },
    getSelectionNoteIndex: () => ({}),
    getSelectionNotesForClauseFromIndex: () => [],
    getSelectionNotesForTarget: () => [],
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
    ensureSelectionMutationAllowed: async () => false,
    inferSourceLanguage: () => "en",
    escapeHtml: (value) => String(value),
    escapeKey: (value) => String(value),
    escapeSelector: (value) => String(value),
    expandNodePath: () => {},
  });

  await controller.addManualSelectionNote();

  assert.equal(state.ui.notes.length, 0);
  assert.equal(state.ui.highlights.length, 0);
  assert.equal(calls.persisted, 0);
});

test("selection note controller deletes note and prunes orphan highlight", () => {
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

  controller.deleteNote("note-1");

  assert.deepEqual(state.ui.notes, []);
  assert.deepEqual(state.ui.highlights, []);
  assert.equal(state.ui.openSelectionNoteIds.size, 0);
  assert.deepEqual(state.ui.selectionNoteOverlayPositions, {});
  assert.equal(calls.persisted, 1);
  assert.deepEqual(calls.rerenderLoadedNodes[0], ["23501:1.1"]);
});
