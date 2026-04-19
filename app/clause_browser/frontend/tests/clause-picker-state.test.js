import test from "node:test";
import assert from "node:assert/strict";

import {
  clearPickerClauseSelection,
  getPickerSelectedClauseIds,
  getSelectedClauseRootIds,
  mergeLoadedClauseRoot,
  nodeIncludesDescendants,
  normalizePickerSelectedClauseIdsBySpec,
  pruneClauseSubtreeToSelection,
  togglePickerClauseSelection,
} from "../static/js/utils/clause-picker-state.js";

const catalog = {
  byId: {
    "4": { clausePath: ["4"] },
    "4.1": { clausePath: ["4", "4.1"] },
    "4.1.1": { clausePath: ["4", "4.1", "4.1.1"] },
    "4.2": { clausePath: ["4", "4.2"] },
    "5": { clausePath: ["5"] },
  },
  childrenByParent: {
    "": ["4", "5"],
    "4": ["4.1", "4.2"],
    "4.1": ["4.1.1"],
  },
};

test("picker selection helpers normalize and cascade descendants from the checked parent", () => {
  const normalized = normalizePickerSelectedClauseIdsBySpec({
    " 23501 ": ["4.1", "4.1", " 4.2 "],
    "": ["1"],
  });

  assert.deepEqual(normalized, { "23501": ["4.1", "4.2"] });
  assert.deepEqual(getPickerSelectedClauseIds(normalized, "23501"), ["4.1", "4.2"]);

  const added = togglePickerClauseSelection({}, "23501", "4", true, catalog);
  assert.deepEqual(new Set(added["23501"]), new Set(["4", "4.1", "4.1.1", "4.2"]));

  const removed = togglePickerClauseSelection(added, "23501", "4.1", false, catalog);
  assert.deepEqual(new Set(removed["23501"]), new Set(["4", "4.2"]));

  assert.deepEqual(clearPickerClauseSelection(removed, "23501"), {});
});

test("picker selection cascade respects filtered visible descendants when provided", () => {
  const filtered = togglePickerClauseSelection(
    {},
    "23501",
    "4",
    true,
    catalog,
    new Set(["4", "4.1"])
  );

  assert.deepEqual(new Set(filtered["23501"]), new Set(["4", "4.1"]));
});

test("selected clause roots collapse selected descendants into top-level fetch roots", () => {
  assert.deepEqual(getSelectedClauseRootIds(catalog, ["4.1", "4.2", "5"]), ["4", "5"]);
});

test("pruneClauseSubtreeToSelection preserves subtree shape from the top-level ancestor", () => {
  const subtree = {
    key: "23501:4",
    specNo: "23501",
    clauseId: "4",
    clausePath: ["4"],
    children: [
      {
        key: "23501:4.1",
        specNo: "23501",
        clauseId: "4.1",
        clausePath: ["4", "4.1"],
        children: [
          {
            key: "23501:4.1.1",
            specNo: "23501",
            clauseId: "4.1.1",
            clausePath: ["4", "4.1", "4.1.1"],
            children: [],
          },
        ],
      },
      {
        key: "23501:4.2",
        specNo: "23501",
        clauseId: "4.2",
        clausePath: ["4", "4.2"],
        children: [],
      },
    ],
  };

  const pruned = pruneClauseSubtreeToSelection(subtree, ["4.1", "4.1.1"]);

  assert.equal(pruned.clauseId, "4");
  assert.equal(pruned.descendantsLoaded, false);
  assert.deepEqual(pruned.children.map((item) => item.clauseId), ["4.1"]);
  assert.equal(pruned.children[0].descendantsLoaded, true);
  assert.deepEqual(pruned.children[0].children.map((item) => item.clauseId), ["4.1.1"]);
});

test("pruneClauseSubtreeToSelection does not keep hidden descendants when a filtered parent is selected", () => {
  const subtree = {
    key: "23501:4",
    specNo: "23501",
    clauseId: "4",
    clausePath: ["4"],
    children: [
      {
        key: "23501:4.1",
        specNo: "23501",
        clauseId: "4.1",
        clausePath: ["4", "4.1"],
        children: [],
      },
      {
        key: "23501:4.2",
        specNo: "23501",
        clauseId: "4.2",
        clausePath: ["4", "4.2"],
        children: [],
      },
    ],
  };

  const pruned = pruneClauseSubtreeToSelection(subtree, ["4", "4.1"]);

  assert.equal(pruned.clauseId, "4");
  assert.equal(pruned.descendantsLoaded, false);
  assert.deepEqual(pruned.children.map((item) => item.clauseId), ["4.1"]);
});

test("mergeLoadedClauseRoot merges later branches into an existing partial top-level subtree", () => {
  const existingRoots = [
    {
      key: "23501:4",
      specNo: "23501",
      clauseId: "4",
      clausePath: ["4"],
      descendantsLoaded: false,
      children: [
        {
          key: "23501:4.1",
          specNo: "23501",
          clauseId: "4.1",
          clausePath: ["4", "4.1"],
          descendantsLoaded: true,
          children: [],
        },
      ],
    },
  ];

  const merged = mergeLoadedClauseRoot(existingRoots, {
    key: "23501:4",
    specNo: "23501",
    clauseId: "4",
    clausePath: ["4"],
    descendantsLoaded: false,
    children: [
      {
        key: "23501:4.2",
        specNo: "23501",
        clauseId: "4.2",
        clausePath: ["4", "4.2"],
        descendantsLoaded: true,
        children: [],
      },
    ],
  });

  assert.equal(merged.length, 1);
  assert.deepEqual(merged[0].children.map((item) => item.clauseId), ["4.2", "4.1"]);
});

test("nodeIncludesDescendants only treats explicit partial wrappers as incomplete", () => {
  assert.equal(nodeIncludesDescendants({}), true);
  assert.equal(nodeIncludesDescendants({ descendantsLoaded: true }), true);
  assert.equal(nodeIncludesDescendants({ descendantsLoaded: false }), false);
});
