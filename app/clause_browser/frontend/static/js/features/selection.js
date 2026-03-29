import {
  addManualSelectionNote,
  elements,
  handleSelectionChange,
  hideSelectionMenu,
  runSelectionAction,
  toggleSelectionHighlight,
} from "../core.js";

export function bindSelectionFeature() {
  document.addEventListener("selectionchange", handleSelectionChange);
  elements.selectionMenu.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", async () => {
      hideSelectionMenu();
      if (button.dataset.action === "translate-selection") {
        await runSelectionAction(button.dataset.targetLanguage || "ko");
        return;
      }
      if (button.dataset.action === "toggle-selection-highlight") {
        toggleSelectionHighlight();
        return;
      }
      if (button.dataset.action === "add-manual-selection-note") {
        addManualSelectionNote();
      }
    });
  });
}
