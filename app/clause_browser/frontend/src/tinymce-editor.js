import tinymce from "tinymce/tinymce";
import "tinymce/icons/default";
import "tinymce/themes/silver";
import "tinymce/models/dom";
import "tinymce/plugins/table";
import "tinymce/plugins/lists";
import "tinymce/plugins/image";
import "tinymce/plugins/autoresize";
import "tinymce/plugins/link";

const editorMap = new WeakMap();

export async function mountClauseEditor(
  element,
  { html = "", onChange = () => {}, onFocus = () => {}, onContextMenu = () => {}, onSelectionChange = () => {} } = {}
) {
  if (!element) {
    return null;
  }
  const existing = editorMap.get(element);
  if (existing) {
    existing.setContent(html || "");
    return existing;
  }

  const editors = await tinymce.init({
    target: element,
    inline: true,
    license_key: "gpl",
    menubar: false,
    toolbar:
      "undo redo | bold italic underline | bullist numlist | table image link | removeformat",
    plugins: "table lists image autoresize link",
    skin: false,
    content_css: false,
    promotion: false,
    branding: false,
    resize: false,
    contextmenu: false,
    convert_urls: false,
    object_resizing: true,
    browser_spellcheck: true,
    elementpath: false,
    statusbar: false,
    table_grid: true,
    forced_root_block: "p",
    valid_elements: "*[*]",
    valid_children: "+body[style]",
    table_toolbar: "tableprops tabledelete | tableinsertrowbefore tableinsertrowafter tabledeleterow | tableinsertcolbefore tableinsertcolafter tabledeletecol",
    content_style: `
      body { font-family: inherit; font-size: 15px; line-height: 1.7; color: #1f3120; }
      p { margin: 0 0 10px; }
      table { border-collapse: collapse; width: 100%; margin: 14px 0; }
      td, th { border: 1px solid #d7ddd2; padding: 8px 10px; vertical-align: top; }
      th { background: #f2f5ee; }
      td[data-mce-selected], th[data-mce-selected] { position: relative; }
      td[data-mce-selected]::selection, th[data-mce-selected]::selection { background: transparent; }
      td[data-mce-selected] *, th[data-mce-selected] * { outline: 0; -webkit-touch-callout: none; user-select: none; }
      td[data-mce-selected]::after, th[data-mce-selected]::after {
        background-color: rgba(180, 215, 255, 0.7);
        border: 1px solid rgba(180, 215, 255, 0.7);
        bottom: -1px;
        content: '';
        left: -1px;
        mix-blend-mode: multiply;
        position: absolute;
        right: -1px;
        top: -1px;
        pointer-events: none;
      }
      .ephox-snooker-resizer-bar { background-color: #b4d7ff; opacity: 0; -webkit-user-select: none; user-select: none; }
      .ephox-snooker-resizer-cols { cursor: col-resize; }
      .ephox-snooker-resizer-rows { cursor: row-resize; }
      .ephox-snooker-resizer-bar.ephox-snooker-resizer-bar-dragging { opacity: 1; }
      img { max-width: 100%; height: auto; display: block; margin: 12px auto; }
    `,
    setup(editor) {
      let changeTimer = 0;
      const emitChange = () => {
        window.clearTimeout(changeTimer);
        changeTimer = window.setTimeout(() => {
          onChange(editor.getContent({ format: "html" }));
        }, 120);
      };
      editor.on("init", () => {
        editor.setContent(html || "");
      });
      editor.on("focus", () => {
        onFocus(editor);
      });
      editor.on("contextmenu", (event) => {
        event.preventDefault();
        const original = event?.originalEvent || event;
        onContextMenu(original, editor);
      });
      editor.on("NodeChange SelectionChange TableSelectionChange click mouseup keyup", () => {
        onSelectionChange(editor);
      });
      editor.on("input change undo redo SetContent ExecCommand TableModified", emitChange);
    },
  });

  const editor = editors[0] || null;
  if (editor) {
    editorMap.set(element, editor);
  }
  return editor;
}

export async function destroyClauseEditorsIn(root) {
  if (!root) {
    return;
  }
  const hosts =
    root instanceof Element && root.matches?.(".clause-editor-host")
      ? [root]
      : [...root.querySelectorAll?.(".clause-editor-host[data-editor-node-key]") || []];
  for (const host of hosts) {
    const editor = editorMap.get(host);
    if (editor) {
      await editor.remove();
      editorMap.delete(host);
    }
  }
}
