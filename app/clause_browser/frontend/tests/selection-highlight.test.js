import test from "node:test";
import assert from "node:assert/strict";

import {
  buildHighlightRowVariants,
  buildRowVariants,
  createHighlightEntry,
  normalizeHighlightText,
  normalizeRowText,
  normalizeTableDisplayText,
} from "../static/js/utils/selection-highlight.js";

test("table text normalization preserves existing collapsing and case rules", () => {
  assert.equal(normalizeTableDisplayText("  a   b  "), "a b");
  assert.equal(normalizeRowText([" A ", "", "B  "]), "a | b");
  assert.equal(normalizeHighlightText("  A   |   B  "), "a | b");
});

test("row variant builders include joined and tail variants", () => {
  assert.deepEqual([...buildRowVariants(["Header", "Value"])].sort(), ["header | value", "header; value", "value"]);
  assert.deepEqual(
    [...buildHighlightRowVariants("Header | Value")].sort(),
    [...new Set(["header | value", "header; value", "value"])].sort()
  );
});

test("createHighlightEntry preserves id and normalized field semantics", () => {
  assert.deepEqual(
    createHighlightEntry({
      clauseKey: " 23501:5.1 ",
      blockId: " block-1 ",
      blockIndex: 3,
      rowIndex: 2,
      cellIndex: 1,
      cellId: " cell-1 ",
      rowText: " Row Text ",
    }),
    {
      id: "manual:23501:5.1:block-1:cell-1:row text",
      type: "manual",
      clauseKey: "23501:5.1",
      blockId: "block-1",
      blockIndex: 3,
      rowIndex: 2,
      cellIndex: 1,
      cellId: "cell-1",
      rowText: "Row Text",
    }
  );
  assert.equal(createHighlightEntry({ clauseKey: "", blockIndex: 0 }), null);
});
