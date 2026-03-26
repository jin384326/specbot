import {
  bindElements,
  bindGlobalEvents,
  elements,
  ensureClauseCatalog,
  loadConfig,
  refreshDocuments,
  renderClauseTree,
  renderLoadedTree,
  renderSelectedClauseList,
  renderSpecbotResults,
  restoreSessionState,
  state,
} from "./core.js";
import { bindDocumentsFeature } from "./features/documents.js";
import { bindExportFeature } from "./features/export.js";
import { bindSelectionFeature } from "./features/selection.js";
import { bindSpecbotFeature } from "./features/specbot.js";
import { bindTreeFeature } from "./features/tree.js";

document.addEventListener("DOMContentLoaded", async () => {
  bindElements();
  bindGlobalEvents();
  bindDocumentsFeature();
  bindSpecbotFeature();
  bindSelectionFeature();
  bindExportFeature();
  bindTreeFeature();

  await loadConfig();
  restoreSessionState();
  await refreshDocuments({ guard: false });
  if (state.activeSpecNo) {
    elements.activeDocumentLabel.textContent = state.activeSpecNo;
    elements.clauseSearch.value = state.ui.clauseQuery || "";
    await ensureClauseCatalog(state.activeSpecNo);
  }
  elements.specbotQuery.value = state.ui.specbotQueryText || "";
  renderLoadedTree();
  renderSelectedClauseList();
  renderSpecbotResults();
  renderClauseTree();
});
