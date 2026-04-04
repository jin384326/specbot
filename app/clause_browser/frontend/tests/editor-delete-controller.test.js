import test from "node:test";
import assert from "node:assert/strict";

import { createEditorDeleteController } from "../static/js/controllers/editor-delete-controller.js";

function createFixture() {
  const state = {
    ui: {
      notes: [],
      highlights: [],
    },
  };
  const elements = {
    treeContainer: {
      querySelectorAll(selector) {
        if (selector === ".table-cell-content[data-clause-key]") {
          return allCells;
        }
        return [];
      },
    },
  };
  const allCells = [
    { dataset: { clauseKey: "23501:1.1", blockIndex: "0", rowIndex: "0", cellIndex: "0", colIndex: "0" } },
    { dataset: { clauseKey: "23501:1.1", blockIndex: "0", rowIndex: "0", cellIndex: "1", colIndex: "1" } },
    { dataset: { clauseKey: "23501:1.1", blockIndex: "0", rowIndex: "1", cellIndex: "0", colIndex: "0" } },
    { dataset: { clauseKey: "23501:1.1", blockIndex: "0", rowIndex: "1", cellIndex: "1", colIndex: "1" } },
  ];
  const calls = {
    persisted: 0,
    rerenderLoadedNode: [],
    rerenderLoadedNodes: [],
    clearTreeSelectionState: 0,
    syncClauseAnnotationBlockReferences: [],
  };
  const controller = createEditorDeleteController({
    state,
    elements,
    updateNodeBlocks: () => false,
    getBlockIdByIndex: () => "block-1",
    blockReferenceMatches: (item, clauseKey, blockIndex, blockId) =>
      item.clauseKey === clauseKey &&
      Number(item.blockIndex) === Number(blockIndex) &&
      String(item.blockId || "") === String(blockId || ""),
    removeBlockAt: (blocks, blockIndex) => blocks.filter((_, index) => index !== blockIndex),
    removeTableRow: (block) => block,
    removeTableColumn: (block) => block,
    syncClauseAnnotationBlockReferences: (clauseKey) => {
      calls.syncClauseAnnotationBlockReferences.push(clauseKey);
    },
    persistSessionState: () => {
      calls.persisted += 1;
    },
    rerenderLoadedNode: (key) => {
      calls.rerenderLoadedNode.push(key);
    },
    rerenderLoadedNodes: (keys) => {
      calls.rerenderLoadedNodes.push(keys);
    },
    clearTreeSelectionState: () => {
      calls.clearTreeSelectionState += 1;
    },
  });

  return { controller, state, calls, allCells };
}

test("editor delete controller builds full-row delete plan for selected row cells", () => {
  const { controller, allCells } = createFixture();
  const selectedCells = [allCells[0], allCells[1]];

  const plan = controller.buildSelectionDeletePlan({
    compareBoundaryPoints() {
      return 0;
    },
    cloneRange() {
      return this;
    },
    selectNodeContents() {},
    setEnd() {},
    toString() {
      return "";
    },
  });

  assert.equal(plan, null);

  const rowPlan = controller.buildSelectionDeletePlan({
    compareBoundaryPoints() {
      return 0;
    },
    cloneRange() {
      return this;
    },
    selectNodeContents() {},
    setEnd() {},
    toString() {
      return "";
    },
  });

  assert.equal(rowPlan, null);
  const directPlan = controller.groupCellsByRow(selectedCells);
  assert.equal(directPlan.get(0).size, 2);
});

test("editor delete controller remaps row and block annotations without changing block-id anchored entries", () => {
  const { controller, state } = createFixture();
  state.ui.notes = [
    { type: "selection", clauseKey: "23501:1.1", blockIndex: 2, blockId: "", rowIndex: -1, cellIndex: -1 },
    { type: "selection", clauseKey: "23501:1.1", blockIndex: 1, blockId: "block-1", rowIndex: 3, cellIndex: 2, cellId: "" },
  ];
  state.ui.highlights = [
    { clauseKey: "23501:1.1", blockIndex: 2, blockId: "", rowIndex: -1, cellIndex: -1 },
    { clauseKey: "23501:1.1", blockIndex: 1, blockId: "block-1", rowIndex: 3, cellIndex: 2, cellId: "" },
  ];

  controller.remapAnnotationsForBlockRemoval("23501:1.1", 1);
  controller.remapAnnotationsForRowRemoval("23501:1.1", 1, 1);
  controller.remapAnnotationsForColumnRemoval("23501:1.1", 1, 1);

  assert.equal(state.ui.notes[0].blockIndex, 1);
  assert.equal(state.ui.highlights[0].blockIndex, 1);
  assert.equal(state.ui.notes[1].rowIndex, 2);
  assert.equal(state.ui.notes[1].cellIndex, 1);
});

test("editor delete controller resyncs table annotations after row deletion", () => {
  const { state, calls } = createFixture();
  const tableBlock = {
    type: "table",
    cells: [
      [{ id: "cell-0-0", text: "A" }, { id: "cell-0-1", text: "B" }],
      [{ id: "cell-1-0", text: "C" }, { id: "cell-1-1", text: "D" }],
    ],
  };
  const controller = createEditorDeleteController({
    state,
    elements: {
      treeContainer: {
        querySelectorAll() {
          return [];
        },
      },
    },
    updateNodeBlocks: (clauseKey, transform) => {
      assert.equal(clauseKey, "23501:1.1");
      const nextBlocks = transform([tableBlock]);
      assert.equal(nextBlocks[0].cells.length, 1);
      return true;
    },
    getBlockIdByIndex: () => "block-1",
    blockReferenceMatches: (item, clauseKey, blockIndex, blockId) =>
      item.clauseKey === clauseKey &&
      Number(item.blockIndex) === Number(blockIndex) &&
      String(item.blockId || "") === String(blockId || ""),
    removeBlockAt: (blocks, blockIndex) => blocks.filter((_, index) => index !== blockIndex),
    removeTableRow: (block, rowIndex) => ({
      ...block,
      cells: block.cells.filter((_, index) => index !== rowIndex),
    }),
    removeTableColumn: (block) => block,
    syncClauseAnnotationBlockReferences: (clauseKey) => {
      calls.syncClauseAnnotationBlockReferences.push(clauseKey);
    },
    persistSessionState: () => {
      calls.persisted += 1;
    },
    rerenderLoadedNode: (key) => {
      calls.rerenderLoadedNode.push(key);
    },
    rerenderLoadedNodes: (keys) => {
      calls.rerenderLoadedNodes.push(keys);
    },
    clearTreeSelectionState: () => {
      calls.clearTreeSelectionState += 1;
    },
  });

  state.ui.notes = [
    {
      type: "selection",
      clauseKey: "23501:1.1",
      blockIndex: 0,
      blockId: "block-1",
      rowIndex: 1,
      cellIndex: 0,
      cellId: "cell-1-0",
    },
  ];
  state.ui.highlights = [
    {
      clauseKey: "23501:1.1",
      blockIndex: 0,
      blockId: "block-1",
      rowIndex: 1,
      cellIndex: 0,
      cellId: "cell-1-0",
    },
  ];

  controller.applySelectionDeletePlan({
    type: "delete-table-rows",
    clauseKey: "23501:1.1",
    blockIndex: 0,
    rowIndexes: [0],
  });

  assert.deepEqual(calls.syncClauseAnnotationBlockReferences, ["23501:1.1"]);
  assert.equal(calls.clearTreeSelectionState, 1);
  assert.equal(calls.persisted, 1);
  assert.deepEqual(calls.rerenderLoadedNode, ["23501:1.1"]);
});

test("editor delete controller remaps selection note targets across multiple row deletions", () => {
  const { controller, state } = createFixture();
  state.ui.notes = [
    {
      id: "note-1",
      type: "selection",
      clauseKey: "23501:1.1",
      blockIndex: 1,
      blockId: "block-1",
      rowIndex: 4,
      cellIndex: -1,
      cellId: "",
      targets: [
        { clauseKey: "23501:1.1", blockIndex: 1, blockId: "block-1", rowIndex: 1, cellIndex: -1, cellId: "" },
        { clauseKey: "23501:1.1", blockIndex: 1, blockId: "block-1", rowIndex: 4, cellIndex: -1, cellId: "" },
      ],
    },
  ];

  controller.remapAnnotationsForRowRemoval("23501:1.1", 1, 3);
  controller.remapAnnotationsForRowRemoval("23501:1.1", 1, 1);

  assert.equal(state.ui.notes.length, 1);
  assert.deepEqual(
    state.ui.notes[0].targets,
    [{ clauseKey: "23501:1.1", blockIndex: 1, blockId: "block-1", rowIndex: 2, cellIndex: -1, cellId: "" }]
  );
});
