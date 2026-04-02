function getTableCellPlacements(cells) {
  const occupied = new Set();
  const items = [];
  let colCount = 0;
  (cells || []).forEach((row, rowIndex) => {
    let colIndex = 0;
    (row || []).forEach((cell) => {
      while (occupied.has(`${rowIndex}:${colIndex}`)) {
        colIndex += 1;
      }
      const rowspan = Math.max(1, Number(cell.rowspan || 1));
      const colspan = Math.max(1, Number(cell.colspan || 1));
      items.push({
        rowIndex,
        colIndex,
        rowspan,
        colspan,
        cell: { ...cell },
      });
      for (let rowOffset = 0; rowOffset < rowspan; rowOffset += 1) {
        for (let colOffset = 0; colOffset < colspan; colOffset += 1) {
          occupied.add(`${rowIndex + rowOffset}:${colIndex + colOffset}`);
        }
      }
      colCount = Math.max(colCount, colIndex + colspan);
      colIndex += colspan;
    });
  });
  return {
    items,
    rowCount: (cells || []).length,
    colCount,
  };
}

function buildCellsFromPlacements(placements, rowCount) {
  if (rowCount <= 0) {
    return [];
  }
  const rows = Array.from({ length: rowCount }, () => []);
  [...placements]
    .sort((left, right) => {
      if (left.rowIndex !== right.rowIndex) {
        return left.rowIndex - right.rowIndex;
      }
      return left.colIndex - right.colIndex;
    })
    .forEach((item) => {
      if (item.rowIndex < 0 || item.rowIndex >= rowCount) {
        return;
      }
      rows[item.rowIndex].push({
        ...item.cell,
        rowspan: item.rowspan,
        colspan: item.colspan,
      });
    });
  return rows;
}

function hasRenderableTableCells(rows) {
  return (rows || []).some((row) => Array.isArray(row) && row.length);
}

function removeTableRowFromCells(cells, rowIndex) {
  const placements = getTableCellPlacements(cells);
  if (rowIndex >= placements.rowCount) {
    return cells;
  }
  const nextPlacements = placements.items
    .flatMap((item) => {
      const start = item.rowIndex;
      const end = item.rowIndex + item.rowspan - 1;
      if (rowIndex < start) {
        return [{ ...item, rowIndex: start - 1 }];
      }
      if (rowIndex > end) {
        return [item];
      }
      if (item.rowspan <= 1 && start === rowIndex) {
        return [];
      }
      return [{ ...item, rowspan: item.rowspan - 1 }];
    })
    .filter((item) => item.rowspan > 0 && item.colspan > 0);
  return buildCellsFromPlacements(nextPlacements, placements.rowCount - 1);
}

function removeTableColumnFromCells(cells, columnIndex) {
  const placements = getTableCellPlacements(cells);
  if (columnIndex >= placements.colCount) {
    return cells;
  }
  const nextPlacements = placements.items
    .flatMap((item) => {
      const start = item.colIndex;
      const end = item.colIndex + item.colspan - 1;
      if (columnIndex < start) {
        return [{ ...item, colIndex: start - 1 }];
      }
      if (columnIndex > end) {
        return [item];
      }
      if (item.colspan <= 1 && start === columnIndex) {
        return [];
      }
      return [{ ...item, colspan: item.colspan - 1 }];
    })
    .filter((item) => item.rowspan > 0 && item.colspan > 0);
  return buildCellsFromPlacements(nextPlacements, placements.rowCount);
}

function removeTableRow(block, rowIndex) {
  if (rowIndex < 0) {
    return block;
  }
  if (Array.isArray(block.cells) && block.cells.length) {
    const transformed = removeTableRowFromCells(block.cells, rowIndex);
    if (!transformed || !transformed.length || !hasRenderableTableCells(transformed)) {
      return null;
    }
    return { ...block, cells: transformed };
  }
  const rows = Array.isArray(block.rows) ? block.rows : [];
  if (rowIndex >= rows.length) {
    return block;
  }
  const nextRows = rows.filter((_, index) => index !== rowIndex);
  if (!nextRows.length) {
    return null;
  }
  return { ...block, rows: nextRows };
}

function removeTableColumn(block, columnIndex) {
  if (columnIndex < 0) {
    return block;
  }
  if (Array.isArray(block.cells) && block.cells.length) {
    const transformed = removeTableColumnFromCells(block.cells, columnIndex);
    if (!transformed || !transformed.length || !hasRenderableTableCells(transformed)) {
      return null;
    }
    return { ...block, cells: transformed };
  }
  const rows = Array.isArray(block.rows) ? block.rows : [];
  if (!rows.length) {
    return block;
  }
  const nextRows = rows
    .map((row) => row.filter((_, index) => index !== columnIndex))
    .filter((row) => row.length);
  if (!nextRows.length || !nextRows[0]?.length) {
    return null;
  }
  return { ...block, rows: nextRows };
}

export {
  removeTableRow,
  removeTableColumn,
  removeTableRowFromCells,
  removeTableColumnFromCells,
};
