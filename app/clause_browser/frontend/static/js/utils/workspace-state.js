export function createWorkspaceSnapshot(state) {
  return {
    activeSpecNo: state.activeSpecNo,
    loadedRoots: state.loadedRoots,
    expandedKeys: [...state.ui.expandedKeys],
    focusedKey: state.ui.focusedKey,
    viewportKey: state.ui.viewportKey,
    collapsedSpecs: [...state.ui.collapsedSpecs],
    collapsedLoadedSpecs: [...state.ui.collapsedLoadedSpecs],
    clauseQuery: state.ui.clauseQuery,
    specbotQueryText: state.ui.specbotQueryText || "",
    specbotSettings: state.ui.specbotSettings,
    boardScope: state.ui.boardScope,
    specbotResults: state.ui.specbotResults,
    specbotResultsCollapsed: Boolean(state.ui.specbotResultsCollapsed),
    notes: state.ui.notes || [],
    highlights: state.ui.highlights || [],
  };
}

export function normalizeWorkspacePayload(payload, dependencies) {
  return {
    activeSpecNo: payload?.activeSpecNo || "",
    loadedRoots: dependencies.ensureForestStableBlockIds(Array.isArray(payload?.loadedRoots) ? payload.loadedRoots : []),
    expandedKeys: new Set(Array.isArray(payload?.expandedKeys) ? payload.expandedKeys : []),
    focusedKey: payload?.focusedKey || "",
    viewportKey: payload?.viewportKey || "",
    collapsedSpecs: new Set(Array.isArray(payload?.collapsedSpecs) ? payload.collapsedSpecs : []),
    collapsedLoadedSpecs: new Set(Array.isArray(payload?.collapsedLoadedSpecs) ? payload.collapsedLoadedSpecs : []),
    clauseQuery: payload?.clauseQuery || "",
    specbotQueryText: payload?.specbotQueryText || "",
    specbotResultsCollapsed: Boolean(payload?.specbotResultsCollapsed),
    notes: Array.isArray(payload?.notes) ? payload.notes : [],
    highlights: Array.isArray(payload?.highlights) ? payload.highlights : [],
    specbotResults: Array.isArray(payload?.specbotResults) ? dependencies.sortSpecbotHits(payload.specbotResults) : [],
    boardScope: {
      releaseData: String(payload?.boardScope?.releaseData || "").trim(),
      release: String(payload?.boardScope?.release || "").trim(),
    },
    specbotSettings:
      payload?.specbotSettings && typeof payload.specbotSettings === "object"
        ? {
            ...payload.specbotSettings,
            rejectedClauses: dependencies.normalizeRejectedClauses(payload.specbotSettings.rejectedClauses),
          }
        : null,
  };
}

export function createEmptyWorkspaceSnapshot({ specbotSettings, boardScope }) {
  return {
    activeSpecNo: "",
    loadedRoots: [],
    expandedKeys: [],
    focusedKey: "",
    viewportKey: "",
    collapsedSpecs: [],
    collapsedLoadedSpecs: [],
    clauseQuery: "",
    specbotQueryText: "",
    specbotResultsCollapsed: false,
    notes: [],
    highlights: [],
    specbotResults: [],
    specbotSettings,
    boardScope,
  };
}
