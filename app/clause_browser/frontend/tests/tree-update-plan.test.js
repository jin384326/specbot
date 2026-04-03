import test from "node:test";
import assert from "node:assert/strict";

import {
  getAffectedClauseKeysForSelectionArtifacts,
  buildFocusNodeUpdatePlan,
} from "../static/js/utils/tree-update-plan.js";

test("getAffectedClauseKeysForSelectionArtifacts collects unique clause keys from note targets", () => {
  const keys = getAffectedClauseKeysForSelectionArtifacts([
    {
      clauseKey: "23501:5.1",
      targets: [
        { clauseKey: "23501:5.1" },
        { clauseKey: "23501:5.2" },
      ],
    },
    {
      clauseKey: "23501:5.2",
    },
  ]);

  assert.deepEqual(keys, ["23501:5.1", "23501:5.2"]);
});

test("buildFocusNodeUpdatePlan avoids structure rerender when only focused key changes", () => {
  const plan = buildFocusNodeUpdatePlan({
    key: "23501:5.2",
    previousFocusedKey: "23501:5.1",
    previousExpandedKeys: new Set(["23501:5", "23501:5.2"]),
    nextExpandedKeys: new Set(["23501:5", "23501:5.2"]),
    previousCollapsedLoadedSpecs: new Set(),
    nextCollapsedLoadedSpecs: new Set(),
  });

  assert.equal(plan.requiresStructureRender, false);
  assert.deepEqual(plan.focusedKeys, ["23501:5.1", "23501:5.2"]);
});

test("buildFocusNodeUpdatePlan requires structure rerender when expansion changes", () => {
  const plan = buildFocusNodeUpdatePlan({
    key: "23501:5.2.1",
    previousFocusedKey: "23501:5.1",
    previousExpandedKeys: new Set(["23501:5"]),
    nextExpandedKeys: new Set(["23501:5", "23501:5.2", "23501:5.2.1"]),
    previousCollapsedLoadedSpecs: new Set(),
    nextCollapsedLoadedSpecs: new Set(),
  });

  assert.equal(plan.requiresStructureRender, true);
});
