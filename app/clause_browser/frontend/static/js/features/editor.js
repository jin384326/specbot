import { mountClauseEditor } from "../vendor/tinymce-editor.js";

function initializeClauseEditors({
  scope,
  findNodeByKey,
  state,
  readOnly = false,
  updateSelectedClauseActiveState,
  buildEditorHtmlFromBlocks,
  ensureBlocksHaveStableIds,
  updateSelectionStateFromEditorSelection,
  hideNodeMenu,
  showSelectionMenu,
  syncEditorHtmlToNode,
}) {
  scope.querySelectorAll(".clause-editor-host[data-editor-node-key]").forEach((element) => {
    const nodeKey = element.dataset.editorNodeKey || "";
    const node = findNodeByKey(nodeKey);
    if (!node) {
      return;
    }
    element.addEventListener("focusin", () => {
      state.ui.focusedKey = nodeKey;
      state.ui.viewportKey = nodeKey;
      updateSelectedClauseActiveState();
    });
    void mountClauseEditor(element, {
      readOnly,
      html: buildEditorHtmlFromBlocks(nodeKey, ensureBlocksHaveStableIds(node.blocks || [])),
      onFocus: () => {
        state.ui.focusedKey = nodeKey;
        state.ui.viewportKey = nodeKey;
        updateSelectedClauseActiveState();
      },
      onContextMenu: (event, editor) => {
        updateSelectionStateFromEditorSelection(editor);
        hideNodeMenu();
        showSelectionMenu(event.clientX || 0, event.clientY || 0);
      },
      onSelectionChange: () => {
        updateSelectionStateFromEditorSelection();
      },
      onChange: (html) => {
        if (!readOnly) {
          syncEditorHtmlToNode(nodeKey, html);
        }
      },
    });
  });
}

export {
  initializeClauseEditors,
};
