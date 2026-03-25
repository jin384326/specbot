import { elements, handleSelectionChange, hideSelectionMenu, runAction } from "../core.js";

export function bindSelectionFeature() {
  elements.runActionButton.addEventListener("click", () => runAction());
  document.addEventListener("selectionchange", handleSelectionChange);
  elements.selectionMenu.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", async () => {
      elements.targetLanguage.value = button.dataset.targetLanguage;
      hideSelectionMenu();
      await runAction();
    });
  });
}
