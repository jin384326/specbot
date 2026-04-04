export function collectLoadedClausePairs(nodes) {
  return (nodes || [])
    .flatMap((node) => [
      { specNo: String(node.specNo || "").trim(), clauseId: String(node.clauseId || "").trim() },
      ...collectLoadedClausePairs(node.children || []),
    ])
    .filter((item) => item.specNo && item.clauseId);
}

export function parseSpecbotExcludeSpecs(text) {
  return String(text || "")
    .split(/\r?\n|,/)
    .map((item) => item.trim())
    .filter(Boolean);
}

export function parseSpecbotExcludeClauses(text) {
  return String(text || "")
    .split(/\r?\n|,/)
    .map((item) => item.trim())
    .filter(Boolean)
    .map((item) => {
      const [specNo, clauseId] = item.split(":");
      return { specNo: String(specNo || "").trim(), clauseId: String(clauseId || "").trim() };
    })
    .filter((item) => item.specNo && item.clauseId);
}

export function dedupeClausePairs(items) {
  const pairs = new Map();
  (items || []).forEach((item) => {
    const specNo = String(item.specNo || "").trim();
    const clauseId = String(item.clauseId || "").trim();
    if (specNo && clauseId) {
      pairs.set(`${specNo}:${clauseId}`, { specNo, clauseId });
    }
  });
  return [...pairs.values()];
}

export function getNormalizedRejectedClauses(items) {
  return dedupeClausePairs(Array.isArray(items) ? items : []);
}

export function buildSpecbotExclusions({ settings = {}, documents = [], loadedRoots = [], rejectedClauses = [], compareMixedToken, compareSpecbotHits }) {
  const includedSpecs = new Set(
    Array.isArray(settings.includedSpecs) && settings.includedSpecs.length
      ? settings.includedSpecs.map((item) => String(item).trim()).filter(Boolean)
      : documents.map((item) => String(item.specNo || "").trim()).filter(Boolean)
  );
  const excludeSpecs = new Set(
    Array.isArray(settings.excludeSpecs) ? settings.excludeSpecs.map((item) => String(item).trim()).filter(Boolean) : []
  );
  documents.forEach((item) => {
    const specNo = String(item.specNo || "").trim();
    if (specNo && !includedSpecs.has(specNo)) {
      excludeSpecs.add(specNo);
    }
  });
  const excludeClauseMap = new Map();

  const manualClauses = Array.isArray(settings.excludeClauses) ? settings.excludeClauses : [];
  manualClauses.forEach((item) => {
    const specNo = String(item.specNo || "").trim();
    const clauseId = String(item.clauseId || "").trim();
    if (specNo && clauseId) {
      excludeClauseMap.set(`${specNo}:${clauseId}`, { specNo, clauseId });
    }
  });

  rejectedClauses.forEach((item) => {
    excludeClauseMap.set(`${item.specNo}:${item.clauseId}`, item);
  });

  collectLoadedClausePairs(loadedRoots).forEach((item) => {
    excludeClauseMap.set(`${item.specNo}:${item.clauseId}`, item);
  });

  return {
    excludeSpecs: [...excludeSpecs].sort(compareMixedToken),
    excludeClauses: [...excludeClauseMap.values()].sort((left, right) => compareSpecbotHits(left, right)),
  };
}

export function filterSpecbotHitsByExclusions(hits, exclusions) {
  const excludeSpecs = new Set((exclusions?.excludeSpecs || []).map((item) => String(item || "").trim()).filter(Boolean));
  const excludeClausePairs = new Set(
    (exclusions?.excludeClauses || [])
      .map((item) => {
        const specNo = String(item.specNo || "").trim();
        const clauseId = String(item.clauseId || "").trim();
        return specNo && clauseId ? `${specNo}:${clauseId}` : "";
      })
      .filter(Boolean)
  );
  return (hits || []).filter((item) => {
    const specNo = String(item.specNo || "").trim();
    const clauseId = String(item.clauseId || "").trim();
    if (!specNo || !clauseId) {
      return false;
    }
    if (excludeSpecs.has(specNo)) {
      return false;
    }
    if (excludeClausePairs.has(`${specNo}:${clauseId}`)) {
      return false;
    }
    return true;
  });
}

export function getIterationsForDepth(depth) {
  if (depth === "short") {
    return 0;
  }
  if (depth === "long") {
    return 2;
  }
  return 1;
}

export function getSpecbotDepthFromSettings(settings = {}) {
  if (settings.queryDepth === "short" || settings.queryDepth === "medium" || settings.queryDepth === "long") {
    return settings.queryDepth;
  }
  const iterations = Number(settings.iterations);
  if (iterations <= 0) {
    return "short";
  }
  if (iterations >= 2) {
    return "long";
  }
  return "medium";
}
