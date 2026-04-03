function createStableBlockId(prefix = "blk") {
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return `${prefix}-${crypto.randomUUID()}`;
  }
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

function createStableCellId() {
  return createStableBlockId("cell");
}

function normalizeEditorText(value) {
  return String(value || "").replace(/\r\n/g, "\n").replace(/\u00a0/g, " ").trim();
}

function ensureBlocksHaveStableIds(blocks) {
  return (blocks || []).map((block) => {
    const nextBlock = {
      ...block,
      id: String(block?.id || "").trim() || createStableBlockId(),
    };
    if (nextBlock.type === "table" && Array.isArray(nextBlock.cells)) {
      return {
        ...nextBlock,
        cells: nextBlock.cells.map((row) =>
          (row || []).map((cell) => ({
            ...cell,
            id: String(cell?.id || "").trim() || createStableCellId(),
          }))
        ),
      };
    }
    return nextBlock;
  });
}

function ensureNodeStableBlockIds(node) {
  if (!node || typeof node !== "object") {
    return node;
  }
  const normalizedText = normalizeEditorText(node.text || "");
  const rawBlocks = Array.isArray(node.blocks) ? node.blocks : [];
  const normalizedBlocks = rawBlocks.length
    ? rawBlocks
    : normalizedText
      ? [{ type: "paragraph", text: normalizedText }]
      : [];
  return {
    ...node,
    blocks: ensureBlocksHaveStableIds(normalizedBlocks),
    children: Array.isArray(node.children) ? node.children.map((child) => ensureNodeStableBlockIds(child)) : [],
  };
}

function ensureForestStableBlockIds(nodes) {
  return (nodes || []).map((node) => ensureNodeStableBlockIds(node));
}

function deriveNodeTextFromBlocks(blocks) {
  return (blocks || [])
    .flatMap((block) => {
      if (block.type === "paragraph") {
        return [String(block.text || "").trim()];
      }
      if (block.type === "table") {
        if (Array.isArray(block.cells) && block.cells.length) {
          return block.cells.flat().map((cell) => String(cell.text || "").trim());
        }
        return (block.rows || []).flat().map((cell) => String(cell || "").trim());
      }
      if (block.type === "image") {
        return [String(block.alt || "").trim()];
      }
      return [];
    })
    .filter(Boolean)
    .join("\n");
}

function removeBlockAt(blocks, blockIndex) {
  if (blockIndex < 0 || blockIndex >= blocks.length) {
    return blocks;
  }
  return blocks.filter((_, index) => index !== blockIndex);
}

export {
  createStableBlockId,
  createStableCellId,
  normalizeEditorText,
  ensureBlocksHaveStableIds,
  ensureNodeStableBlockIds,
  ensureForestStableBlockIds,
  deriveNodeTextFromBlocks,
  removeBlockAt,
};
