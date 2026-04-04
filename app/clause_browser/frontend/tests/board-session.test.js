import test from "node:test";
import assert from "node:assert/strict";

import {
  clearBoardEditorSession,
  readBoardEditorSession,
  shouldPreferSessionWorkspace,
  writeBoardEditorSession,
} from "../static/js/utils/board-session.js";

function createStorage() {
  const store = new Map();
  return {
    getItem(key) {
      return store.has(key) ? store.get(key) : null;
    },
    setItem(key, value) {
      store.set(key, String(value));
    },
    removeItem(key) {
      store.delete(key);
    },
  };
}

test("board editor session helpers round-trip session metadata", () => {
  const storage = createStorage();

  writeBoardEditorSession({ postId: "post-1", mode: "edit" }, storage);
  assert.deepEqual(readBoardEditorSession(storage), { postId: "post-1", mode: "edit" });

  clearBoardEditorSession(storage);
  assert.equal(readBoardEditorSession(storage), null);
});

test("shouldPreferSessionWorkspace only prefers the same edit post", () => {
  assert.equal(shouldPreferSessionWorkspace({ postId: "post-1", mode: "edit" }, "post-1", "edit"), true);
  assert.equal(shouldPreferSessionWorkspace({ postId: "post-1", mode: "view" }, "post-1", "edit"), false);
  assert.equal(shouldPreferSessionWorkspace({ postId: "post-2", mode: "edit" }, "post-1", "edit"), false);
  assert.equal(shouldPreferSessionWorkspace({ postId: "post-1", mode: "edit" }, "post-1", "view"), false);
});
