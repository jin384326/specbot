function getUniqueClauseKeys(keys = []) {
  return [...new Set((keys || []).map((key) => String(key || "").trim()).filter(Boolean))];
}

function getAffectedClauseKeysForSelectionArtifacts(artifacts = []) {
  const keys = (artifacts || []).flatMap((item) => {
    if (!item) {
      return [];
    }
    const explicitTargets = Array.isArray(item.targets) ? item.targets : [];
    if (explicitTargets.length) {
      return explicitTargets.map((target) => target?.clauseKey || "");
    }
    return [item.clauseKey || ""];
  });
  return getUniqueClauseKeys(keys);
}

function buildFocusNodeUpdatePlan({
  key,
  previousFocusedKey = "",
  nextExpandedKeys = new Set(),
  previousExpandedKeys = new Set(),
  nextCollapsedLoadedSpecs = new Set(),
  previousCollapsedLoadedSpecs = new Set(),
} = {}) {
  const normalizedKey = String(key || "").trim();
  const focusedKeys = getUniqueClauseKeys([previousFocusedKey, normalizedKey]);
  const expansionChanged =
    nextExpandedKeys.size !== previousExpandedKeys.size ||
    [...nextExpandedKeys].some((item) => !previousExpandedKeys.has(item));
  const collapsedSpecChanged =
    nextCollapsedLoadedSpecs.size !== previousCollapsedLoadedSpecs.size ||
    [...nextCollapsedLoadedSpecs].some((item) => !previousCollapsedLoadedSpecs.has(item));
  return {
    requiresStructureRender: expansionChanged || collapsedSpecChanged,
    focusedKeys,
  };
}

export {
  getAffectedClauseKeysForSelectionArtifacts,
  buildFocusNodeUpdatePlan,
};
