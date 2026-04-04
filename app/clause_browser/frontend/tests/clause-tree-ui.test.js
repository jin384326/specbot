import test from "node:test";
import assert from "node:assert/strict";

import {
  buildLoadedSpecGroupHtml,
  buildSelectedClauseCard,
  buildSelectedClauseListHtml,
  compareClausePart,
  compareLoadedNodes,
  compareMixedToken,
  groupRootsBySpec,
} from "../static/js/utils/clause-tree-ui.js";

const escapeHtml = (value) => String(value);

test("clause comparators preserve numeric-aware ordering", () => {
  assert.equal(compareMixedToken("10", "2") > 0, true);
  assert.equal(compareClausePart("4.2.2.10", "4.2.2.2") > 0, true);
  assert.equal(compareLoadedNodes({ specNo: "23502", clausePath: ["4.2.2.2"] }, { specNo: "23501", clausePath: ["5"] }) > 0, true);
});

test("groupRootsBySpec keeps nodes grouped by spec in sorted order", () => {
  const grouped = groupRootsBySpec([
    { specNo: "23502", clauseId: "2", clausePath: ["2"] },
    { specNo: "23501", clauseId: "5", clausePath: ["5"] },
    { specNo: "23501", clauseId: "4", clausePath: ["4"] },
  ]);
  assert.deepEqual(Object.keys(grouped), ["23501", "23502"]);
  assert.deepEqual(grouped["23501"].map((item) => item.clauseId), ["4", "5"]);
});

test("selected clause and loaded spec html builders preserve expected controls", () => {
  const renderCard = (node, depth) =>
    buildSelectedClauseCard(node, depth, {
      escapeHtml,
      isActive: node.key === "k1",
      renderChildren(children, nextDepth) {
        return children.map((child) => renderCard(child, nextDepth)).join("");
      },
    });

  const selectedHtml = buildSelectedClauseListHtml({
    groupedRoots: { "23501": [{ key: "k1", clauseId: "5", clauseTitle: "Title", children: [] }] },
    collapsedSpecs: new Set(),
    escapeHtml,
    renderCard,
  });
  assert.match(selectedHtml, /data-action="toggle-selected-spec"/);
  assert.match(selectedHtml, /data-action="focus-selected"/);

  const loadedHtml = buildLoadedSpecGroupHtml({
    specNo: "23501",
    nodes: [{ key: "k1" }],
    collapsed: false,
    clauseCount: 1,
    escapeHtml,
    renderNode: () => "<article>node</article>",
  });
  assert.match(loadedHtml, /data-action="toggle-loaded-spec"/);
  assert.match(loadedHtml, /1 clauses loaded/);
});
