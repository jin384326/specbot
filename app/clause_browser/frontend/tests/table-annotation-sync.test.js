import test from "node:test";
import assert from "node:assert/strict";

import { remapTableAnnotationsForEditorChange } from "../static/js/utils/table-annotation-sync.js";
import { normalizeRowText, normalizeTableDisplayText } from "../static/js/utils/selection-highlight.js";

test("table annotation sync remaps row-level note to shifted row after editor row deletion", () => {
  const previousBlocks = [
    {
      id: "block-1",
      type: "table",
      cells: [
        [{ id: "a1", text: "A1" }],
        [{ id: "b1", text: "B1" }],
        [{ id: "c1", text: "C1" }],
      ],
    },
  ];
  const nextBlocks = [
    {
      id: "block-1",
      type: "table",
      cells: [
        [{ id: "a1", text: "A1" }],
        [{ id: "c1", text: "C1" }],
      ],
    },
  ];

  const [note] = remapTableAnnotationsForEditorChange(
    [{
      id: "note-1",
      type: "selection",
      clauseKey: "23501:1.1",
      blockId: "block-1",
      blockIndex: 0,
      rowIndex: 2,
      cellIndex: -1,
      cellId: "",
      rowText: "C1",
    }],
    "23501:1.1",
    previousBlocks,
    nextBlocks,
    { normalizeRowText, normalizeTableDisplayText }
  );

  assert.equal(note.rowIndex, 1);
  assert.equal(note.rowText, "c1");
});

test("table annotation sync removes row-level note when its row is deleted in editor", () => {
  const previousBlocks = [
    {
      id: "block-1",
      type: "table",
      cells: [
        [{ id: "a1", text: "A1" }],
        [{ id: "b1", text: "B1" }],
      ],
    },
  ];
  const nextBlocks = [
    {
      id: "block-1",
      type: "table",
      cells: [
        [{ id: "a1", text: "A1" }],
      ],
    },
  ];

  const notes = remapTableAnnotationsForEditorChange(
    [{
      id: "note-1",
      type: "selection",
      clauseKey: "23501:1.1",
      blockId: "block-1",
      blockIndex: 0,
      rowIndex: 1,
      cellIndex: -1,
      cellId: "",
      rowText: "B1",
    }],
    "23501:1.1",
    previousBlocks,
    nextBlocks,
    { normalizeRowText, normalizeTableDisplayText }
  );

  assert.deepEqual(notes, []);
});
