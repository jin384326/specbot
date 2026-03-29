import { debounce, elements, openPicker, refreshDocuments, renderClauseTree, state } from "../core.js";

export function bindDocumentsFeature() {
  elements.openPickerButton.addEventListener("click", async () => {
    await openPicker();
  });
  elements.documentSearch.addEventListener("input", debounce(() => refreshDocuments({ silent: true }), 250));
  elements.clauseSearch.addEventListener(
    "input",
    debounce(() => {
      state.ui.clauseQuery = elements.clauseSearch.value.trim();
      refreshDocuments({ silent: true });
      renderClauseTree();
    }, 180)
  );
}
