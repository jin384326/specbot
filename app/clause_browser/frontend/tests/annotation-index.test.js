import test from "node:test";
import assert from "node:assert/strict";

import {
  createSelectionNoteIndex,
  createHighlightIndex,
  getSelectionNotesForTargetFromIndex,
  getSelectionNotesForClauseFromIndex,
  getHighlightsForBlockFromIndex,
  getGlobalRowHighlightsForClauseFromIndex,
} from "../static/js/utils/annotation-index.js";

const resolveBlockIndex = (_clauseKey, blockIndex, blockId = "") => {
  if (blockId === "block-from-id") {
    return 7;
  }
  return Number(blockIndex ?? -1);
};

test("selection note index maps multi-target table notes to each selected row", () => {
  const notes = [
    {
      id: "note-1",
      type: "selection",
      clauseKey: "23501:5.27.2.1",
      blockId: "table-1",
      blockIndex: 3,
      rowIndex: 0,
      cellIndex: -1,
      cellId: "",
      targets: [
        {
          clauseKey: "23501:5.27.2.1",
          blockId: "table-1",
          blockIndex: 3,
          rowIndex: 2,
          cellIndex: -1,
          cellId: "",
        },
        {
          clauseKey: "23501:5.27.2.1",
          blockId: "table-1",
          blockIndex: 3,
          rowIndex: 3,
          cellIndex: -1,
          cellId: "",
        },
      ],
    },
  ];

  const index = createSelectionNoteIndex(notes, resolveBlockIndex);

  assert.deepEqual(
    getSelectionNotesForTargetFromIndex(index, "23501:5.27.2.1", 3, 2, -1, "table-1", "").map((note) => note.id),
    ["note-1"]
  );
  assert.deepEqual(
    getSelectionNotesForTargetFromIndex(index, "23501:5.27.2.1", 3, 3, -1, "table-1", "").map((note) => note.id),
    ["note-1"]
  );
});

test("selection note index falls back to the note anchor when explicit targets are missing", () => {
  const notes = [
    {
      id: "note-2",
      type: "selection",
      clauseKey: "23501:4.1.1",
      blockId: "block-from-id",
      blockIndex: -1,
      rowIndex: -1,
      cellIndex: -1,
      cellId: "",
    },
  ];

  const index = createSelectionNoteIndex(notes, resolveBlockIndex);

  assert.deepEqual(
    getSelectionNotesForClauseFromIndex(index, "23501:4.1.1").map((note) => note.id),
    ["note-2"]
  );
  assert.deepEqual(
    getSelectionNotesForTargetFromIndex(index, "23501:4.1.1", 7, -1, -1, "block-from-id", "").map((note) => note.id),
    ["note-2"]
  );
});

test("highlight index groups local block highlights and per-clause global row highlights", () => {
  const highlights = [
    {
      id: "highlight-block",
      clauseKey: "23501:5.27.2.1",
      blockId: "table-1",
      blockIndex: 3,
      rowIndex: 2,
      cellIndex: -1,
      cellId: "",
      rowText: "row 3",
    },
    {
      id: "highlight-global-row",
      clauseKey: "23501:5.27.2.1",
      blockId: "",
      blockIndex: -1,
      rowIndex: 4,
      cellIndex: -1,
      cellId: "",
      rowText: "row 5",
    },
  ];

  const index = createHighlightIndex(highlights, resolveBlockIndex);

  assert.deepEqual(
    getHighlightsForBlockFromIndex(index, "23501:5.27.2.1", 3, "table-1").map((item) => item.id),
    ["highlight-block"]
  );
  assert.deepEqual(
    getGlobalRowHighlightsForClauseFromIndex(index, "23501:5.27.2.1").map((item) => item.id),
    ["highlight-global-row"]
  );
});
