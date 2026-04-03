function createEmptyIndex() {
  return {
    byClause: new Map(),
    byTarget: new Map(),
  };
}

function createBlockKey(clauseKey, resolvedBlockIndex, blockId = "") {
  return `${String(clauseKey || "").trim()}::${String(blockId || "").trim() || Number(resolvedBlockIndex ?? -1)}`;
}

function createTargetKey(clauseKey, resolvedBlockIndex, rowIndex = -1, cellIndex = -1, blockId = "", cellId = "") {
  return [
    createBlockKey(clauseKey, resolvedBlockIndex, blockId),
    Number(rowIndex ?? -1),
    String(cellId || "").trim() || Number(cellIndex ?? -1),
  ].join("::");
}

function appendIndexEntry(map, key, value) {
  const existing = map.get(key) || [];
  existing.push(value);
  map.set(key, existing);
}

function getResolvedBlockIndex(resolveBlockIndex, clauseKey, blockIndex, blockId = "") {
  return typeof resolveBlockIndex === "function"
    ? Number(resolveBlockIndex(clauseKey, blockIndex, blockId))
    : Number(blockIndex ?? -1);
}

function getNoteTargets(note) {
  const explicitTargets = Array.isArray(note?.targets) ? note.targets.filter(Boolean) : [];
  if (explicitTargets.length) {
    return explicitTargets;
  }
  return [
    {
      clauseKey: note?.clauseKey || "",
      blockId: note?.blockId || "",
      blockIndex: note?.blockIndex ?? -1,
      rowIndex: note?.rowIndex ?? -1,
      cellIndex: note?.cellIndex ?? -1,
      cellId: note?.cellId || "",
    },
  ];
}

function createSelectionNoteIndex(notes = [], resolveBlockIndex = null) {
  const index = createEmptyIndex();
  (notes || []).forEach((note) => {
    if (note?.type !== "selection") {
      return;
    }
    const clauseKey = String(note.clauseKey || "").trim();
    if (!clauseKey) {
      return;
    }
    appendIndexEntry(index.byClause, clauseKey, note);
    const seenTargetKeys = new Set();
    getNoteTargets(note).forEach((target) => {
      const targetClauseKey = String(target?.clauseKey || clauseKey).trim();
      const targetBlockId = String(target?.blockId || "").trim();
      const resolvedBlockIndex = getResolvedBlockIndex(resolveBlockIndex, targetClauseKey, target?.blockIndex ?? -1, targetBlockId);
      const targetKey = createTargetKey(
        targetClauseKey,
        resolvedBlockIndex,
        Number(target?.rowIndex ?? -1),
        Number(target?.cellIndex ?? -1),
        targetBlockId,
        String(target?.cellId || "").trim()
      );
      if (seenTargetKeys.has(targetKey)) {
        return;
      }
      seenTargetKeys.add(targetKey);
      appendIndexEntry(index.byTarget, targetKey, note);
    });
  });
  return index;
}

function getSelectionNotesForClauseFromIndex(index, clauseKey) {
  return [...(index?.byClause?.get(String(clauseKey || "").trim()) || [])];
}

function getSelectionNotesForTargetFromIndex(index, clauseKey, blockIndex, rowIndex = -1, cellIndex = null, blockId = "", cellId = "", resolveBlockIndex = null) {
  const normalizedClauseKey = String(clauseKey || "").trim();
  const normalizedBlockId = String(blockId || "").trim();
  const resolvedBlockIndex = getResolvedBlockIndex(resolveBlockIndex, normalizedClauseKey, blockIndex, normalizedBlockId);
  const normalizedCellId = String(cellId || "").trim();
  const targetKey = createTargetKey(
    normalizedClauseKey,
    resolvedBlockIndex,
    Number(rowIndex ?? -1),
    cellIndex === null ? -1 : Number(cellIndex ?? -1),
    normalizedBlockId,
    normalizedCellId
  );
  return [...(index?.byTarget?.get(targetKey) || [])];
}

function createHighlightIndex(highlights = [], resolveBlockIndex = null) {
  return {
    byBlock: (highlights || []).reduce((map, item) => {
      const clauseKey = String(item?.clauseKey || "").trim();
      if (!clauseKey) {
        return map;
      }
      const blockIndex = Number(item?.blockIndex ?? -1);
      const blockId = String(item?.blockId || "").trim();
      if (blockIndex < 0 && !blockId) {
        return map;
      }
      const resolvedBlockIndex = getResolvedBlockIndex(resolveBlockIndex, clauseKey, blockIndex, blockId);
      appendIndexEntry(map, createBlockKey(clauseKey, resolvedBlockIndex, blockId), item);
      return map;
    }, new Map()),
    globalRowsByClause: (highlights || []).reduce((map, item) => {
      const clauseKey = String(item?.clauseKey || "").trim();
      if (!clauseKey) {
        return map;
      }
      if (Number(item?.blockIndex ?? -1) >= 0 || String(item?.blockId || "").trim()) {
        return map;
      }
      if (Number(item?.rowIndex ?? -1) < 0 || Number(item?.cellIndex ?? -1) >= 0) {
        return map;
      }
      appendIndexEntry(map, clauseKey, item);
      return map;
    }, new Map()),
  };
}

function getHighlightsForBlockFromIndex(index, clauseKey, blockIndex, blockId = "", resolveBlockIndex = null) {
  const normalizedClauseKey = String(clauseKey || "").trim();
  const normalizedBlockId = String(blockId || "").trim();
  const resolvedBlockIndex = getResolvedBlockIndex(resolveBlockIndex, normalizedClauseKey, blockIndex, normalizedBlockId);
  return [...(index?.byBlock?.get(createBlockKey(normalizedClauseKey, resolvedBlockIndex, normalizedBlockId)) || [])];
}

function getGlobalRowHighlightsForClauseFromIndex(index, clauseKey) {
  return [...(index?.globalRowsByClause?.get(String(clauseKey || "").trim()) || [])];
}

export {
  createSelectionNoteIndex,
  createHighlightIndex,
  getSelectionNotesForTargetFromIndex,
  getSelectionNotesForClauseFromIndex,
  getHighlightsForBlockFromIndex,
  getGlobalRowHighlightsForClauseFromIndex,
};
