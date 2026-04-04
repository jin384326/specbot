export function compareMixedToken(left, right) {
  const leftMatch = String(left).match(/^(\d+)(.*)$/);
  const rightMatch = String(right).match(/^(\d+)(.*)$/);
  if (leftMatch && rightMatch) {
    const numberCompare = Number(leftMatch[1]) - Number(rightMatch[1]);
    if (numberCompare !== 0) {
      return numberCompare;
    }
    return leftMatch[2].localeCompare(rightMatch[2]);
  }
  return String(left).localeCompare(String(right), undefined, { numeric: true });
}

export function compareClausePart(left, right) {
  const leftTokens = String(left).split(".");
  const rightTokens = String(right).split(".");
  const length = Math.max(leftTokens.length, rightTokens.length);
  for (let index = 0; index < length; index += 1) {
    const tokenCompare = compareMixedToken(leftTokens[index] ?? "", rightTokens[index] ?? "");
    if (tokenCompare !== 0) {
      return tokenCompare;
    }
  }
  return 0;
}

export function compareLoadedNodes(left, right) {
  const specCompare = compareMixedToken(String(left.specNo || ""), String(right.specNo || ""));
  if (specCompare !== 0) {
    return specCompare;
  }
  const leftPath = left.clausePath || [left.clauseId || ""];
  const rightPath = right.clausePath || [right.clauseId || ""];
  const pathLength = Math.max(leftPath.length, rightPath.length);
  for (let index = 0; index < pathLength; index += 1) {
    const leftPart = leftPath[index] ?? "";
    const rightPart = rightPath[index] ?? "";
    const partCompare = compareClausePart(leftPart, rightPart);
    if (partCompare !== 0) {
      return partCompare;
    }
  }
  return 0;
}

export function groupRootsBySpec(roots) {
  return [...roots].sort(compareLoadedNodes).reduce((groups, node) => {
    const next = { ...groups };
    const existing = next[node.specNo] || [];
    next[node.specNo] = [...existing, node];
    return next;
  }, {});
}

export function buildSelectedClauseCard(node, depth, { escapeHtml, isActive, renderChildren }) {
  return `
    <div class="selected-clause-row ${isActive ? "active" : ""}" data-selected-key="${escapeHtml(node.key)}" style="margin-left:${depth * 12}px">
      <span class="selected-clause-bullet">-</span>
      <button class="selected-clause-link" data-action="focus-selected" data-node-key="${escapeHtml(node.key)}">
        ${escapeHtml(node.clauseId)} ${escapeHtml(node.clauseTitle)}
      </button>
    </div>
    ${renderChildren(node.children || [], depth + 1)}
  `;
}

export function buildSelectedClauseListHtml({ groupedRoots, collapsedSpecs, escapeHtml, renderCard }) {
  return Object.entries(groupedRoots)
    .map(
      ([specNo, nodes]) => `
        <section class="selected-spec-group">
          <div class="selected-spec-title">
            <button class="selected-spec-toggle" data-action="toggle-selected-spec" data-spec-no="${escapeHtml(specNo)}">
              ${collapsedSpecs.has(specNo) ? "+" : "−"}
            </button>
            <span>${escapeHtml(specNo)}</span>
          </div>
          ${collapsedSpecs.has(specNo) ? "" : nodes.map((node) => renderCard(node, 0)).join("")}
        </section>
      `
    )
    .join("");
}

export function buildLoadedSpecGroupHtml({ specNo, nodes, collapsed, clauseCount, escapeHtml, renderNode }) {
  return `
    <section class="tree-spec-group">
      <article class="tree-node tree-spec-root">
        <div class="tree-header tree-spec-header">
          <div class="tree-title">
            <button data-action="toggle-loaded-spec" data-spec-no="${escapeHtml(specNo)}">${collapsed ? "+" : "−"}</button>
            <div class="tree-title-text">
              <h3>${escapeHtml(specNo)}</h3>
              <div class="tree-meta">${clauseCount} clauses loaded</div>
            </div>
          </div>
        </div>
        ${collapsed ? "" : `<div class="tree-body tree-spec-body"><div class="tree-spec-children">${nodes.map((node) => renderNode(node)).join("")}</div></div>`}
      </article>
    </section>
  `;
}
