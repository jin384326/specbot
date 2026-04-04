function isVisible(element) {
  return element instanceof HTMLElement && !element.classList.contains("hidden") && element.offsetParent !== null;
}

export function bindEditorSaveShortcutFeature() {
  document.addEventListener("keydown", (event) => {
    const isSaveShortcut = (event.ctrlKey || event.metaKey) && String(event.key || "").toLowerCase() === "s";
    if (!isSaveShortcut) {
      return;
    }
    const saveButton = document.getElementById("board-save-post");
    if (!(saveButton instanceof HTMLButtonElement) || !isVisible(saveButton) || saveButton.disabled) {
      return;
    }
    event.preventDefault();
    saveButton.click();
  });
}
