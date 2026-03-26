import { elements, handleSelectionChange, hideSelectionMenu, runSelectionAction } from "../core.js";

export function bindSelectionFeature() {
  document.addEventListener("selectionchange", handleSelectionChange);
  elements.selectionMenu.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", async () => {
      hideSelectionMenu();
      await runSelectionAction(button.dataset.targetLanguage || "ko");
    });
  });
}
