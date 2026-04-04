const BOARD_EDITOR_SESSION_KEY = "specbot-board-editor-session-v1";

export function readBoardEditorSession(storage = window.sessionStorage) {
  try {
    const raw = storage.getItem(BOARD_EDITOR_SESSION_KEY);
    if (!raw) {
      return null;
    }
    const parsed = JSON.parse(raw);
    const postId = String(parsed?.postId || "").trim();
    const mode = String(parsed?.mode || "").trim();
    if (!mode) {
      return null;
    }
    return { postId, mode };
  } catch (_error) {
    return null;
  }
}

export function writeBoardEditorSession(session, storage = window.sessionStorage) {
  storage.setItem(
    BOARD_EDITOR_SESSION_KEY,
    JSON.stringify({
      postId: String(session?.postId || "").trim(),
      mode: String(session?.mode || "").trim(),
    })
  );
}

export function clearBoardEditorSession(storage = window.sessionStorage) {
  storage.removeItem(BOARD_EDITOR_SESSION_KEY);
}

export function shouldPreferSessionWorkspace(session, postId, mode) {
  const normalizedPostId = String(postId || "").trim();
  const normalizedMode = String(mode || "").trim();
  const sessionPostId = String(session?.postId || "").trim();
  const sessionMode = String(session?.mode || "").trim();
  return normalizedMode === "edit" && Boolean(normalizedPostId) && sessionMode === "edit" && sessionPostId === normalizedPostId;
}
