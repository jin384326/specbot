export function createEditorDeleteController(dependencies) {
  const {
    state,
    elements,
    updateNodeBlocks,
    getBlockIdByIndex,
    blockReferenceMatches,
    removeBlockAt,
    removeTableRow,
    removeTableColumn,
    syncClauseAnnotationBlockReferences = () => {},
    persistSessionState,
    rerenderLoadedNode,
    rerenderLoadedNodes,
    clearTreeSelectionState,
  } = dependencies;

  function getIntersectedElements(range, selector) {
    return [...elements.treeContainer.querySelectorAll(selector)].filter((element) => {
      try {
        const elementRange = document.createRange();
        elementRange.selectNodeContents(element);
        const startsBeforeElementEnds = range.compareBoundaryPoints(Range.START_TO_END, elementRange) < 0;
        const endsAfterElementStarts = range.compareBoundaryPoints(Range.END_TO_START, elementRange) > 0;
        return startsBeforeElementEnds && endsAfterElementStarts;
      } catch (_error) {
        return false;
      }
    });
  }

  function groupCellsByRow(cells) {
    return cells.reduce((map, cell) => {
      const rowIndex = Number(cell.dataset.rowIndex || -1);
      const cellIndex = Number(cell.dataset.cellIndex || -1);
      if (rowIndex < 0 || cellIndex < 0) {
        return map;
      }
      const existing = map.get(rowIndex) || new Set();
      existing.add(cellIndex);
      map.set(rowIndex, existing);
      return map;
    }, new Map());
  }

  function groupCellsByColumn(cells) {
    return cells.reduce((map, cell) => {
      const columnIndex = Number(cell.dataset.colIndex || -1);
      const rowIndex = Number(cell.dataset.rowIndex || -1);
      if (columnIndex < 0 || rowIndex < 0) {
        return map;
      }
      const existing = map.get(columnIndex) || new Set();
      existing.add(rowIndex);
      map.set(columnIndex, existing);
      return map;
    }, new Map());
  }

  function getRangeOffsetsWithinElement(range, element) {
    try {
      const startRange = range.cloneRange();
      startRange.selectNodeContents(element);
      startRange.setEnd(range.startContainer, range.startOffset);
      const endRange = range.cloneRange();
      endRange.selectNodeContents(element);
      endRange.setEnd(range.endContainer, range.endOffset);
      return {
        start: startRange.toString().length,
        end: endRange.toString().length,
      };
    } catch (_error) {
      return null;
    }
  }

  function buildParagraphDeletePlan(range, paragraph) {
    const clauseKey = paragraph.dataset.clauseKey || "";
    const blockIndex = Number(paragraph.dataset.blockIndex || -1);
    const offsets = getRangeOffsetsWithinElement(range, paragraph);
    if (!clauseKey || blockIndex < 0 || !offsets || offsets.end <= offsets.start) {
      return null;
    }
    return {
      type: "paragraph-text",
      clauseKey,
      blockIndex,
      start: offsets.start,
      end: offsets.end,
    };
  }

  function buildMultiParagraphDeletePlan(paragraphs) {
    const blockTargets = paragraphs
      .map((element) => ({
        clauseKey: element.dataset.clauseKey || "",
        blockIndex: Number(element.dataset.blockIndex || -1),
      }))
      .filter((item) => item.clauseKey && item.blockIndex >= 0);
    if (!blockTargets.length) {
      return null;
    }
    return { type: "remove-blocks", blockTargets };
  }

  function buildTableDeletePlan(range, cells) {
    const first = cells[0];
    const clauseKey = first.dataset.clauseKey || "";
    const blockIndex = Number(first.dataset.blockIndex || -1);
    const multipleBlocks = cells.some(
      (cell) => cell.dataset.clauseKey !== clauseKey || Number(cell.dataset.blockIndex || -1) !== blockIndex
    );
    if (multipleBlocks) {
      return {
        type: "remove-blocks",
        blockTargets: cells.map((cell) => ({
          clauseKey: cell.dataset.clauseKey || "",
          blockIndex: Number(cell.dataset.blockIndex || -1),
        })),
      };
    }
    const sameBlockCells = cells.filter(
      (cell) => cell.dataset.clauseKey === clauseKey && Number(cell.dataset.blockIndex || -1) === blockIndex
    );
    const allCells = [...elements.treeContainer.querySelectorAll(".table-cell-content[data-clause-key]")]
      .filter((cell) => cell.dataset.clauseKey === clauseKey && Number(cell.dataset.blockIndex || -1) === blockIndex);
    if (sameBlockCells.length === allCells.length) {
      return { type: "remove-blocks", blockTargets: [{ clauseKey, blockIndex }] };
    }

    const selectedByRow = groupCellsByRow(sameBlockCells);
    const allByRow = groupCellsByRow(allCells);
    const selectedRows = [...selectedByRow.keys()].filter((rowIndex) => {
      const selectedCols = selectedByRow.get(rowIndex) || new Set();
      const allCols = allByRow.get(rowIndex) || new Set();
      return selectedCols.size > 0 && selectedCols.size === allCols.size;
    });
    if (selectedRows.length) {
      return { type: "delete-table-rows", clauseKey, blockIndex, rowIndexes: selectedRows.sort((a, b) => b - a) };
    }

    const selectedByColumn = groupCellsByColumn(sameBlockCells);
    const allByColumn = groupCellsByColumn(allCells);
    const selectedColumns = [...selectedByColumn.keys()].filter((columnIndex) => {
      const selectedRowsForColumn = selectedByColumn.get(columnIndex) || new Set();
      const allRowsForColumn = allByColumn.get(columnIndex) || new Set();
      return selectedRowsForColumn.size > 0 && selectedRowsForColumn.size === allRowsForColumn.size;
    });
    if (selectedColumns.length) {
      return { type: "delete-table-columns", clauseKey, blockIndex, columnIndexes: selectedColumns.sort((a, b) => b - a) };
    }

    if (sameBlockCells.length === 1) {
      const textHolder = sameBlockCells[0].querySelector(".table-cell-text");
      if (textHolder) {
        const offsets = getRangeOffsetsWithinElement(range, textHolder);
        if (offsets && offsets.end > offsets.start) {
          return {
            type: "table-cell-text",
            clauseKey,
            blockIndex,
            rowIndex: Number(sameBlockCells[0].dataset.rowIndex || -1),
            cellIndex: Number(sameBlockCells[0].dataset.cellIndex || -1),
            start: offsets.start,
            end: offsets.end,
          };
        }
      }
    }
    return { type: "remove-blocks", blockTargets: [{ clauseKey, blockIndex }] };
  }

  function buildSelectionDeletePlan(range) {
    const paragraphs = getIntersectedElements(range, ".docx-paragraph[data-clause-key]");
    const cells = getIntersectedElements(range, ".table-cell-content[data-clause-key]");
    if (paragraphs.length && cells.length) {
      return {
        type: "remove-blocks",
        blockTargets: [
          ...paragraphs.map((element) => ({
            clauseKey: element.dataset.clauseKey || "",
            blockIndex: Number(element.dataset.blockIndex || -1),
          })),
          ...cells.map((element) => ({
            clauseKey: element.dataset.clauseKey || "",
            blockIndex: Number(element.dataset.blockIndex || -1),
          })),
        ],
      };
    }
    if (paragraphs.length === 1 && !cells.length) {
      return buildParagraphDeletePlan(range, paragraphs[0]);
    }
    if (cells.length) {
      return buildTableDeletePlan(range, cells);
    }
    if (paragraphs.length > 1) {
      return buildMultiParagraphDeletePlan(paragraphs);
    }
    return null;
  }

  function remapAnnotationsForBlockRemoval(clauseKey, blockIndex) {
    const remapSelectionTargetsForBlockRemoval = (targets) => {
      if (!Array.isArray(targets) || !targets.length) {
        return null;
      }
      const mappedTargets = targets.flatMap((target) => {
        if (target.clauseKey !== clauseKey) {
          return [target];
        }
        const currentBlockId = String(target.blockId || "").trim();
        if (currentBlockId) {
          return Number(target.blockIndex ?? -1) === Number(blockIndex) ? [] : [target];
        }
        const currentBlockIndex = Number(target.blockIndex ?? -1);
        if (currentBlockIndex === blockIndex) {
          return [];
        }
        if (currentBlockIndex > blockIndex) {
          return [{ ...target, blockIndex: currentBlockIndex - 1 }];
        }
        return [target];
      });
      return mappedTargets.length ? mappedTargets : null;
    };
    state.ui.notes = (state.ui.notes || []).flatMap((note) => {
      if (note.type !== "selection" || note.clauseKey !== clauseKey) {
        return [note];
      }
      const nextTargets = remapSelectionTargetsForBlockRemoval(note.targets);
      if (Array.isArray(note.targets) && note.targets.length && !nextTargets) {
        return [];
      }
      if (String(note.blockId || "").trim()) {
        return [{ ...note, ...(nextTargets ? { targets: nextTargets } : {}) }];
      }
      const currentBlockIndex = Number(note.blockIndex ?? -1);
      if (currentBlockIndex === blockIndex) {
        return [];
      }
      if (currentBlockIndex > blockIndex) {
        return [{ ...note, blockIndex: currentBlockIndex - 1, ...(nextTargets ? { targets: nextTargets } : {}) }];
      }
      return [{ ...note, ...(nextTargets ? { targets: nextTargets } : {}) }];
    });
    state.ui.highlights = (state.ui.highlights || []).flatMap((item) => {
      if (item.clauseKey !== clauseKey) {
        return [item];
      }
      if (String(item.blockId || "").trim()) {
        return [item];
      }
      const currentBlockIndex = Number(item.blockIndex ?? -1);
      if (currentBlockIndex === blockIndex) {
        return [];
      }
      if (currentBlockIndex > blockIndex) {
        return [{ ...item, blockIndex: currentBlockIndex - 1 }];
      }
      return [item];
    });
  }

  function remapAnnotationsForRowRemoval(clauseKey, blockIndex, rowIndex) {
    const blockId = getBlockIdByIndex(clauseKey, blockIndex);
    const remapSelectionTargetsForRowRemoval = (targets) => {
      if (!Array.isArray(targets) || !targets.length) {
        return null;
      }
      const mappedTargets = targets.flatMap((target) => {
        if (!blockReferenceMatches(target, clauseKey, blockIndex, blockId)) {
          return [target];
        }
        if (String(target.cellId || "").trim()) {
          return [target];
        }
        const currentRowIndex = Number(target.rowIndex ?? -1);
        if (currentRowIndex < 0) {
          return [target];
        }
        if (currentRowIndex === rowIndex) {
          return [];
        }
        if (currentRowIndex > rowIndex) {
          return [{ ...target, rowIndex: currentRowIndex - 1 }];
        }
        return [target];
      });
      return mappedTargets.length ? mappedTargets : null;
    };
    state.ui.notes = (state.ui.notes || []).flatMap((note) => {
      if (note.type !== "selection" || !blockReferenceMatches(note, clauseKey, blockIndex, blockId)) {
        return [note];
      }
      const nextTargets = remapSelectionTargetsForRowRemoval(note.targets);
      if (Array.isArray(note.targets) && note.targets.length && !nextTargets) {
        return [];
      }
      if (String(note.cellId || "").trim()) {
        return [{ ...note, ...(nextTargets ? { targets: nextTargets } : {}) }];
      }
      const currentRowIndex = Number(note.rowIndex ?? -1);
      if (currentRowIndex < 0) {
        return [{ ...note, ...(nextTargets ? { targets: nextTargets } : {}) }];
      }
      if (currentRowIndex === rowIndex) {
        return [];
      }
      if (currentRowIndex > rowIndex) {
        return [{ ...note, rowIndex: currentRowIndex - 1, ...(nextTargets ? { targets: nextTargets } : {}) }];
      }
      return [{ ...note, ...(nextTargets ? { targets: nextTargets } : {}) }];
    });
    state.ui.highlights = (state.ui.highlights || []).flatMap((item) => {
      if (!blockReferenceMatches(item, clauseKey, blockIndex, blockId)) {
        return [item];
      }
      if (String(item.cellId || "").trim()) {
        return [item];
      }
      const currentRowIndex = Number(item.rowIndex ?? -1);
      if (currentRowIndex < 0) {
        return [item];
      }
      if (currentRowIndex === rowIndex) {
        return [];
      }
      if (currentRowIndex > rowIndex) {
        return [{ ...item, rowIndex: currentRowIndex - 1 }];
      }
      return [item];
    });
  }

  function remapAnnotationsForColumnRemoval(clauseKey, blockIndex, columnIndex) {
    const blockId = getBlockIdByIndex(clauseKey, blockIndex);
    const remapSelectionTargetsForColumnRemoval = (targets) => {
      if (!Array.isArray(targets) || !targets.length) {
        return null;
      }
      const mappedTargets = targets.flatMap((target) => {
        if (!blockReferenceMatches(target, clauseKey, blockIndex, blockId)) {
          return [target];
        }
        if (String(target.cellId || "").trim()) {
          return [target];
        }
        const currentCellIndex = Number(target.cellIndex ?? -1);
        if (currentCellIndex < 0) {
          return [target];
        }
        if (currentCellIndex === columnIndex) {
          return [];
        }
        if (currentCellIndex > columnIndex) {
          return [{ ...target, cellIndex: currentCellIndex - 1 }];
        }
        return [target];
      });
      return mappedTargets.length ? mappedTargets : null;
    };
    state.ui.notes = (state.ui.notes || []).flatMap((note) => {
      if (note.type !== "selection" || !blockReferenceMatches(note, clauseKey, blockIndex, blockId)) {
        return [note];
      }
      const nextTargets = remapSelectionTargetsForColumnRemoval(note.targets);
      if (Array.isArray(note.targets) && note.targets.length && !nextTargets) {
        return [];
      }
      if (String(note.cellId || "").trim()) {
        return [{ ...note, ...(nextTargets ? { targets: nextTargets } : {}) }];
      }
      const currentCellIndex = Number(note.cellIndex ?? -1);
      if (currentCellIndex < 0) {
        return [{ ...note, ...(nextTargets ? { targets: nextTargets } : {}) }];
      }
      if (currentCellIndex === columnIndex) {
        return [];
      }
      if (currentCellIndex > columnIndex) {
        return [{ ...note, cellIndex: currentCellIndex - 1, ...(nextTargets ? { targets: nextTargets } : {}) }];
      }
      return [{ ...note, ...(nextTargets ? { targets: nextTargets } : {}) }];
    });
    state.ui.highlights = (state.ui.highlights || []).flatMap((item) => {
      if (!blockReferenceMatches(item, clauseKey, blockIndex, blockId)) {
        return [item];
      }
      if (String(item.cellId || "").trim()) {
        return [item];
      }
      const currentCellIndex = Number(item.cellIndex ?? -1);
      if (currentCellIndex < 0) {
        return [item];
      }
      if (currentCellIndex === columnIndex) {
        return [];
      }
      if (currentCellIndex > columnIndex) {
        return [{ ...item, cellIndex: currentCellIndex - 1 }];
      }
      return [item];
    });
  }

  function deleteParagraphText(plan) {
    let removedBlock = false;
    const changed = updateNodeBlocks(plan.clauseKey, (blocks) => {
      const block = blocks[plan.blockIndex];
      if (!block || block.type !== "paragraph") {
        return blocks;
      }
      const text = String(block.text || "");
      const nextText = `${text.slice(0, plan.start)}${text.slice(plan.end)}`;
      if (!nextText.trim()) {
        removedBlock = true;
        return removeBlockAt(blocks, plan.blockIndex);
      }
      return blocks.map((item, index) => (index === plan.blockIndex ? { ...item, text: nextText } : item));
    });
    if (!changed) {
      return;
    }
    if (removedBlock) {
      remapAnnotationsForBlockRemoval(plan.clauseKey, plan.blockIndex);
    }
    clearTreeSelectionState();
    persistSessionState();
    rerenderLoadedNode(plan.clauseKey);
  }

  function deleteTableCellText(plan) {
    const changed = updateNodeBlocks(plan.clauseKey, (blocks) => {
      const block = blocks[plan.blockIndex];
      if (!block || block.type !== "table") {
        return blocks;
      }
      if (Array.isArray(block.cells) && block.cells.length) {
        const nextCells = block.cells.map((row, rowIndex) =>
          row.map((cell, cellIndex) => {
            if (rowIndex !== plan.rowIndex || cellIndex !== plan.cellIndex) {
              return cell;
            }
            const text = String(cell.text || "");
            return { ...cell, text: `${text.slice(0, plan.start)}${text.slice(plan.end)}` };
          })
        );
        return blocks.map((item, index) => (index === plan.blockIndex ? { ...item, cells: nextCells } : item));
      }
      const nextRows = (block.rows || []).map((row, rowIndex) =>
        row.map((cell, cellIndex) => {
          if (rowIndex !== plan.rowIndex || cellIndex !== plan.cellIndex) {
            return cell;
          }
          const text = String(cell || "");
          return `${text.slice(0, plan.start)}${text.slice(plan.end)}`;
        })
      );
      return blocks.map((item, index) => (index === plan.blockIndex ? { ...item, rows: nextRows } : item));
    });
    if (!changed) {
      return;
    }
    clearTreeSelectionState();
    persistSessionState();
    rerenderLoadedNode(plan.clauseKey);
  }

  function deleteSelectedTableRows(plan) {
    let removedBlock = false;
    const changed = updateNodeBlocks(plan.clauseKey, (blocks) => {
      const block = blocks[plan.blockIndex];
      if (!block || block.type !== "table") {
        return blocks;
      }
      let nextBlock = block;
      for (const rowIndex of plan.rowIndexes) {
        nextBlock = removeTableRow(nextBlock, rowIndex);
        if (!nextBlock) {
          removedBlock = true;
          return removeBlockAt(blocks, plan.blockIndex);
        }
      }
      return blocks.map((item, index) => (index === plan.blockIndex ? nextBlock : item));
    });
    if (!changed) {
      return;
    }
    if (removedBlock) {
      remapAnnotationsForBlockRemoval(plan.clauseKey, plan.blockIndex);
    } else {
      plan.rowIndexes.forEach((rowIndex) => remapAnnotationsForRowRemoval(plan.clauseKey, plan.blockIndex, rowIndex));
      syncClauseAnnotationBlockReferences(plan.clauseKey);
    }
    clearTreeSelectionState();
    persistSessionState();
    rerenderLoadedNode(plan.clauseKey);
  }

  function deleteSelectedTableColumns(plan) {
    let removedBlock = false;
    const changed = updateNodeBlocks(plan.clauseKey, (blocks) => {
      const block = blocks[plan.blockIndex];
      if (!block || block.type !== "table") {
        return blocks;
      }
      let nextBlock = block;
      for (const columnIndex of plan.columnIndexes) {
        nextBlock = removeTableColumn(nextBlock, columnIndex);
        if (!nextBlock) {
          removedBlock = true;
          return removeBlockAt(blocks, plan.blockIndex);
        }
      }
      return blocks.map((item, index) => (index === plan.blockIndex ? nextBlock : item));
    });
    if (!changed) {
      return;
    }
    if (removedBlock) {
      remapAnnotationsForBlockRemoval(plan.clauseKey, plan.blockIndex);
    } else {
      plan.columnIndexes.forEach((columnIndex) => remapAnnotationsForColumnRemoval(plan.clauseKey, plan.blockIndex, columnIndex));
      syncClauseAnnotationBlockReferences(plan.clauseKey);
    }
    clearTreeSelectionState();
    persistSessionState();
    rerenderLoadedNode(plan.clauseKey);
  }

  function removeSelectedBlocks(blockTargets) {
    const grouped = blockTargets.reduce((map, item) => {
      const key = item.clauseKey;
      const existing = map.get(key) || [];
      existing.push(Number(item.blockIndex));
      map.set(key, existing);
      return map;
    }, new Map());

    grouped.forEach((indexes, clauseKey) => {
      const uniqueIndexes = [...new Set(indexes)].sort((a, b) => b - a);
      const changed = updateNodeBlocks(clauseKey, (blocks) => {
        let nextBlocks = blocks;
        uniqueIndexes.forEach((blockIndex) => {
          nextBlocks = removeBlockAt(nextBlocks, blockIndex);
        });
        return nextBlocks;
      });
      if (!changed) {
        return;
      }
      uniqueIndexes.forEach((blockIndex) => remapAnnotationsForBlockRemoval(clauseKey, blockIndex));
    });

    clearTreeSelectionState();
    persistSessionState();
    rerenderLoadedNodes([...grouped.keys()]);
  }

  function applySelectionDeletePlan(plan) {
    if (plan.type === "paragraph-text") {
      deleteParagraphText(plan);
      return;
    }
    if (plan.type === "table-cell-text") {
      deleteTableCellText(plan);
      return;
    }
    if (plan.type === "delete-table-rows") {
      deleteSelectedTableRows(plan);
      return;
    }
    if (plan.type === "delete-table-columns") {
      deleteSelectedTableColumns(plan);
      return;
    }
    if (plan.type === "remove-blocks") {
      removeSelectedBlocks(plan.blockTargets);
    }
  }

  function deleteImageBlockFromElement(element) {
    const clauseKey = element.dataset.clauseKey || "";
    const blockIndex = Number(element.dataset.blockIndex || -1);
    if (!clauseKey || blockIndex < 0) {
      return;
    }
    const changed = updateNodeBlocks(clauseKey, (blocks) => removeBlockAt(blocks, blockIndex));
    if (!changed) {
      return;
    }
    remapAnnotationsForBlockRemoval(clauseKey, blockIndex);
    clearTreeSelectionState();
    persistSessionState();
    rerenderLoadedNode(clauseKey);
  }

  return {
    buildSelectionDeletePlan,
    applySelectionDeletePlan,
    deleteImageBlockFromElement,
    groupCellsByRow,
    groupCellsByColumn,
    getRangeOffsetsWithinElement,
    remapAnnotationsForBlockRemoval,
    remapAnnotationsForRowRemoval,
    remapAnnotationsForColumnRemoval,
  };
}
