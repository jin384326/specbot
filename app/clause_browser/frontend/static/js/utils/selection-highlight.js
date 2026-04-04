export function normalizeRowText(parts) {
  return String((parts || []).map((item) => String(item || "").trim()).filter(Boolean).join(" | "))
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase();
}

export function normalizeTableDisplayText(value) {
  return String(value || "")
    .replace(/\s+/g, " ")
    .trim();
}

export function normalizeHighlightText(value) {
  return String(value || "").replace(/\s+/g, " ").trim().toLowerCase();
}

export function buildRowVariants(parts) {
  const normalizedParts = (parts || []).map((item) => normalizeTableDisplayText(item)).filter(Boolean);
  const variants = new Set();
  if (!normalizedParts.length) {
    return variants;
  }
  variants.add(normalizeHighlightText(normalizedParts.join(" | ")));
  variants.add(normalizeHighlightText(normalizedParts.join("; ")));
  if (normalizedParts.length > 1) {
    variants.add(normalizeHighlightText(normalizedParts.slice(1).join(" | ")));
    variants.add(normalizeHighlightText(normalizedParts.slice(1).join("; ")));
  }
  return variants;
}

export function buildHighlightRowVariants(value) {
  const normalized = normalizeHighlightText(value);
  const variants = new Set();
  if (!normalized) {
    return variants;
  }
  variants.add(normalized);
  const pipeParts = normalized.split("|").map((item) => item.trim()).filter(Boolean);
  if (pipeParts.length) {
    variants.add(normalizeHighlightText(pipeParts.join(" | ")));
    variants.add(normalizeHighlightText(pipeParts.join("; ")));
    if (pipeParts.length > 1) {
      variants.add(normalizeHighlightText(pipeParts.slice(1).join(" | ")));
      variants.add(normalizeHighlightText(pipeParts.slice(1).join("; ")));
    }
  }
  const semicolonParts = normalized.split(";").map((item) => item.trim()).filter(Boolean);
  if (semicolonParts.length) {
    variants.add(normalizeHighlightText(semicolonParts.join(" | ")));
    variants.add(normalizeHighlightText(semicolonParts.join("; ")));
    if (semicolonParts.length > 1) {
      variants.add(normalizeHighlightText(semicolonParts.slice(1).join(" | ")));
      variants.add(normalizeHighlightText(semicolonParts.slice(1).join("; ")));
    }
  }
  return variants;
}

export function createHighlightEntry({ clauseKey, blockId = "", blockIndex = -1, rowIndex = -1, cellIndex = -1, cellId = "", rowText = "" }) {
  const normalizedClauseKey = String(clauseKey || "").trim();
  const normalizedBlockId = String(blockId || "").trim();
  const normalizedBlockIndex = Number(blockIndex ?? -1);
  if (!normalizedClauseKey || (!normalizedBlockId && normalizedBlockIndex < 0)) {
    return null;
  }
  const normalizedRowIndex = Number(rowIndex ?? -1);
  const normalizedCellIndex = Number(cellIndex ?? -1);
  const normalizedCellId = String(cellId || "").trim();
  const normalizedRowText = String(rowText || "").trim();
  return {
    id: `manual:${normalizedClauseKey}:${normalizedBlockId || normalizedBlockIndex}:${normalizedCellId || `${normalizedRowIndex}:${normalizedCellIndex}`}:${normalizeHighlightText(normalizedRowText) || "block"}`,
    type: "manual",
    clauseKey: normalizedClauseKey,
    blockId: normalizedBlockId,
    blockIndex: normalizedBlockIndex,
    rowIndex: normalizedRowIndex,
    cellIndex: normalizedCellIndex,
    cellId: normalizedCellId,
    rowText: normalizedRowText,
  };
}
