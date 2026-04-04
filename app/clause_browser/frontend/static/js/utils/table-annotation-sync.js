function findBlockByReference(blocks, blockIndex, blockId = "") {
  const normalizedBlockId = String(blockId || "").trim();
  if (normalizedBlockId) {
    return (blocks || []).find((block) => String(block?.id || "").trim() === normalizedBlockId) || null;
  }
  const resolvedBlockIndex = Number(blockIndex ?? -1);
  return resolvedBlockIndex >= 0 ? (blocks || [])[resolvedBlockIndex] || null : null;
}

function buildRowCellIds(row = []) {
  return (row || []).map((cell) => String(cell?.id || "").trim()).filter(Boolean);
}

function buildRowText(row = [], normalizeRowText, normalizeTableDisplayText) {
  return normalizeRowText((row || []).map((cell) => normalizeTableDisplayText(cell?.text || "")));
}

function findMatchingRowIndex(previousRow, nextRows, normalizeRowText, normalizeTableDisplayText) {
  const previousCellIds = new Set(buildRowCellIds(previousRow));
  if (previousCellIds.size) {
    const matchedIndex = (nextRows || []).findIndex((row) =>
      (row || []).some((cell) => previousCellIds.has(String(cell?.id || "").trim()))
    );
    if (matchedIndex >= 0) {
      return matchedIndex;
    }
  }
  const previousRowText = buildRowText(previousRow, normalizeRowText, normalizeTableDisplayText);
  if (!previousRowText) {
    return -1;
  }
  return (nextRows || []).findIndex(
    (row) => buildRowText(row, normalizeRowText, normalizeTableDisplayText) === previousRowText
  );
}

function remapRowAnchoredReference(item, previousBlocks, nextBlocks, normalizeRowText, normalizeTableDisplayText) {
  if (!item) {
    return null;
  }
  if (String(item.cellId || "").trim()) {
    return item;
  }
  const currentRowIndex = Number(item.rowIndex ?? -1);
  if (currentRowIndex < 0) {
    return item;
  }
  const previousBlock = findBlockByReference(previousBlocks, item.blockIndex, item.blockId);
  const nextBlock = findBlockByReference(nextBlocks, item.blockIndex, item.blockId);
  if (
    previousBlock?.type !== "table" ||
    nextBlock?.type !== "table" ||
    !Array.isArray(previousBlock.cells) ||
    !Array.isArray(nextBlock.cells)
  ) {
    return item;
  }
  const previousRow = previousBlock.cells[currentRowIndex];
  if (!Array.isArray(previousRow) || !previousRow.length) {
    return item;
  }
  const nextRowIndex = findMatchingRowIndex(previousRow, nextBlock.cells, normalizeRowText, normalizeTableDisplayText);
  if (nextRowIndex < 0) {
    return null;
  }
  const nextRow = nextBlock.cells[nextRowIndex] || [];
  return {
    ...item,
    blockId: String(nextBlock.id || item.blockId || ""),
    rowIndex: nextRowIndex,
    rowText: buildRowText(nextRow, normalizeRowText, normalizeTableDisplayText),
  };
}

function sortTargets(targets = []) {
  return [...targets].sort((left, right) =>
    String(left.clauseKey || "").localeCompare(String(right.clauseKey || "")) ||
    Number(left.blockIndex ?? -1) - Number(right.blockIndex ?? -1) ||
    Number(left.rowIndex ?? -1) - Number(right.rowIndex ?? -1) ||
    Number(left.cellIndex ?? -1) - Number(right.cellIndex ?? -1)
  );
}

function remapTableAnnotationsForEditorChange(
  items = [],
  clauseKey,
  previousBlocks,
  nextBlocks,
  { normalizeRowText, normalizeTableDisplayText }
) {
  const normalizedClauseKey = String(clauseKey || "").trim();
  return (items || []).flatMap((item) => {
    if (String(item?.clauseKey || "").trim() !== normalizedClauseKey) {
      return [item];
    }
    const explicitTargets = Array.isArray(item?.targets) ? item.targets.filter(Boolean) : [];
    if (explicitTargets.length) {
      const remappedTargets = explicitTargets.flatMap((target) => {
        const nextTarget = remapRowAnchoredReference(
          target,
          previousBlocks,
          nextBlocks,
          normalizeRowText,
          normalizeTableDisplayText
        );
        return nextTarget ? [nextTarget] : [];
      });
      if (!remappedTargets.length) {
        return [];
      }
      const sortedTargets = sortTargets(remappedTargets);
      const anchorTarget = sortedTargets[0] || null;
      if (!anchorTarget) {
        return [];
      }
      return [{
        ...item,
        clauseKey: String(anchorTarget.clauseKey || item.clauseKey || ""),
        blockIndex: Number(anchorTarget.blockIndex ?? item.blockIndex ?? -1),
        blockId: String(anchorTarget.blockId || item.blockId || ""),
        rowIndex: Number(anchorTarget.rowIndex ?? item.rowIndex ?? -1),
        cellIndex: Number(anchorTarget.cellIndex ?? item.cellIndex ?? -1),
        cellId: String(anchorTarget.cellId || item.cellId || ""),
        rowText: String(anchorTarget.rowText || item.rowText || ""),
        targets: sortedTargets,
      }];
    }
    const remappedItem = remapRowAnchoredReference(
      item,
      previousBlocks,
      nextBlocks,
      normalizeRowText,
      normalizeTableDisplayText
    );
    return remappedItem ? [remappedItem] : [];
  });
}

export {
  remapTableAnnotationsForEditorChange,
};
