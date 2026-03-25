import { addParentClause, elements, hideNodeMenu, state } from "../core.js";

export function bindTreeFeature() {
  elements.nodeMenuAddParent.addEventListener("click", async () => {
    const key = state.ui.nodeMenu.key;
    hideNodeMenu();
    if (key) {
      await addParentClause(key);
    }
  });
}
