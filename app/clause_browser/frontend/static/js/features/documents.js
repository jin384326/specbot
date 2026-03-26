import { debounce, elements, openPicker, refreshDocuments, renderClauseTree, state } from "../core.js";

export function bindDocumentsFeature() {
  elements.openPickerButton.addEventListener("click", openPicker);
  elements.documentSearch.addEventListener("input", debounce(() => refreshDocuments(), 250));
  elements.clauseSearch.addEventListener(
    "input",
    debounce(() => {
      state.ui.clauseQuery = elements.clauseSearch.value.trim();
      refreshDocuments();
      renderClauseTree();
    }, 180)
  );
}
