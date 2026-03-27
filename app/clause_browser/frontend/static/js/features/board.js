import {
  applyWorkspaceSnapshot,
  getWorkspaceSnapshot,
  resetWorkspace,
} from "../core.js";

const EDITOR_ID_KEY = "specbot-board-editor-id-v1";
const EDITOR_LABEL_KEY = "specbot-board-editor-label-v1";
const HEARTBEAT_INTERVAL_MS = 30_000;

const boardState = {
  currentPostId: "",
  currentLock: null,
  heartbeatId: 0,
  mode: "list",
};

function editorId() {
  const existing = window.localStorage.getItem(EDITOR_ID_KEY);
  if (existing) {
    return existing;
  }
  const next = typeof crypto !== "undefined" && crypto.randomUUID ? crypto.randomUUID() : `editor-${Date.now()}`;
  window.localStorage.setItem(EDITOR_ID_KEY, next);
  return next;
}

function editorLabel() {
  const existing = window.localStorage.getItem(EDITOR_LABEL_KEY);
  if (existing) {
    return existing;
  }
  const label = `Editor ${editorId().slice(0, 8)}`;
  window.localStorage.setItem(EDITOR_LABEL_KEY, label);
  return label;
}

function boardElements() {
  return {
    boardScreen: document.getElementById("board-screen"),
    editorScreen: document.getElementById("editor-screen"),
    boardSearch: document.getElementById("board-search"),
    boardCreatePost: document.getElementById("board-create-post"),
    boardListCount: document.getElementById("board-list-count"),
    boardMessageBar: document.getElementById("board-message-bar"),
    boardPostList: document.getElementById("board-post-list"),
    boardBackToList: document.getElementById("board-back-to-list"),
    boardSavePost: document.getElementById("board-save-post"),
    boardPostTitle: document.getElementById("board-post-title"),
    openPickerButton: document.getElementById("open-picker-button"),
    exportButton: document.getElementById("export-button"),
  };
}

function setBoardMessage(text, isError = false) {
  const el = boardElements().boardMessageBar;
  el.innerHTML = text ? `<div class="message ${isError ? "error" : ""}">${escapeHtml(text)}</div>` : "";
}

function setLockStatus(text) {
  const el = document.getElementById("board-lock-status");
  if (el) {
    el.textContent = text;
  }
}

function showBoardScreen() {
  boardState.mode = "list";
  boardElements().boardScreen.classList.remove("hidden");
  boardElements().editorScreen.classList.add("hidden");
}

function showEditorScreen() {
  boardElements().boardScreen.classList.add("hidden");
  boardElements().editorScreen.classList.remove("hidden");
}

function applyEditorMode(mode) {
  boardState.mode = mode;
  const els = boardElements();
  const isEdit = mode === "edit";
  const isView = mode === "view";
  els.boardSavePost.classList.toggle("hidden", !isEdit);
  els.exportButton.classList.toggle("hidden", !isView);
  els.boardPostTitle.readOnly = !isEdit;
  if (els.openPickerButton) {
    els.openPickerButton.classList.toggle("hidden", isView);
  }
}

async function request(url, options = {}) {
  const response = await fetch(url, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = payload?.detail;
    if (detail && typeof detail === "object" && detail.message) {
      throw new Error(String(detail.message));
    }
    throw new Error(String(detail || "Request failed"));
  }
  return payload.data;
}

function renderBoardPosts(items) {
  const { boardPostList, boardListCount } = boardElements();
  boardListCount.textContent = `${items.length} posts`;
  if (!items.length) {
    boardPostList.innerHTML = '<div class="muted">게시글이 없습니다.</div>';
    return;
  }
  boardPostList.innerHTML = items
    .map((item) => {
      const lock = item.lock;
      const lockText = lock ? `편집 중: ${lock.editorLabel}` : "편집 가능";
      return `
        <article class="board-post-card">
          <div class="board-post-main">
            <div class="board-post-title">${escapeHtml(item.title || "Untitled post")}</div>
            <div class="board-post-meta">
              <span>${escapeHtml(item.updatedAt || "")}</span>
              <span>${escapeHtml(lockText)}</span>
            </div>
          </div>
          <div class="board-post-actions">
            <button class="ghost" data-action="view-post" data-post-id="${escapeHtml(item.postId)}">조회</button>
            <button class="primary" data-action="edit-post" data-post-id="${escapeHtml(item.postId)}">편집</button>
          </div>
        </article>
      `;
    })
    .join("");
  boardPostList.querySelectorAll("[data-action='edit-post']").forEach((button) => {
    button.addEventListener("click", async () => {
      await openExistingPost(button.dataset.postId || "");
    });
  });
  boardPostList.querySelectorAll("[data-action='view-post']").forEach((button) => {
    button.addEventListener("click", async () => {
      await openExistingPostReadOnly(button.dataset.postId || "");
    });
  });
}

async function refreshBoardPosts() {
  const query = encodeURIComponent(boardElements().boardSearch.value.trim());
  const data = await request(`/api/clause-browser/board/posts?query=${query}`);
  renderBoardPosts(data.items || []);
}

function startHeartbeat() {
  stopHeartbeat();
  if (!boardState.currentPostId || !boardState.currentLock) {
    return;
  }
  boardState.heartbeatId = window.setInterval(async () => {
    try {
      const data = await request(`/api/clause-browser/board/posts/${boardState.currentPostId}/lock/heartbeat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ editorId: editorId(), editorLabel: editorLabel() }),
      });
      boardState.currentLock = data;
    } catch (error) {
      stopHeartbeat();
      setBoardMessage(error.message, true);
    }
  }, HEARTBEAT_INTERVAL_MS);
}

function stopHeartbeat() {
  if (boardState.heartbeatId) {
    window.clearInterval(boardState.heartbeatId);
    boardState.heartbeatId = 0;
  }
}

async function createPost() {
  const data = await request("/api/clause-browser/board/posts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      title: "새 게시글",
      editorId: editorId(),
      editorLabel: editorLabel(),
    }),
  });
  await openPostInEditor(data);
}

async function openExistingPostReadOnly(postId) {
  const data = await request(`/api/clause-browser/board/posts/${postId}`);
  await openPostInViewer(data);
}

async function openExistingPost(postId) {
  await request(`/api/clause-browser/board/posts/${postId}/lock/acquire`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ editorId: editorId(), editorLabel: editorLabel() }),
  });
  const data = await request(`/api/clause-browser/board/posts/${postId}`);
  await openPostInEditor(data);
}

async function openPostInEditor(post) {
  boardState.currentPostId = post.postId;
  boardState.currentLock = post.lock || null;
  boardElements().boardPostTitle.value = post.title || "";
  showEditorScreen();
  applyEditorMode("edit");
  await resetWorkspace();
  await applyWorkspaceSnapshot(post.workspaceState || {});
  startHeartbeat();
}

async function openPostInViewer(post) {
  boardState.currentPostId = post.postId;
  boardState.currentLock = null;
  boardElements().boardPostTitle.value = post.title || "";
  showEditorScreen();
  applyEditorMode("view");
  stopHeartbeat();
  await resetWorkspace();
  await applyWorkspaceSnapshot(post.workspaceState || {});
}

async function saveCurrentPost() {
  if (!boardState.currentPostId) {
    return;
  }
  const payload = {
    editorId: editorId(),
    editorLabel: editorLabel(),
    title: boardElements().boardPostTitle.value.trim() || "Untitled post",
    body: "",
    workspaceState: getWorkspaceSnapshot(),
  };
  const data = await request(`/api/clause-browser/board/posts/${boardState.currentPostId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  boardState.currentLock = data.lock || null;
  setBoardMessage("게시글을 저장했습니다.", false);
  await closeEditor();
}

async function closeEditor() {
  stopHeartbeat();
  if (boardState.currentPostId) {
    try {
      await request(`/api/clause-browser/board/posts/${boardState.currentPostId}/lock/release`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ editorId: editorId(), editorLabel: editorLabel() }),
      });
    } catch (_error) {
      // ignore
    }
  }
  boardState.currentPostId = "";
  boardState.currentLock = null;
  showBoardScreen();
  await refreshBoardPosts();
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function debounce(fn, wait) {
  let timeoutId = 0;
  return (...args) => {
    window.clearTimeout(timeoutId);
    timeoutId = window.setTimeout(() => fn(...args), wait);
  };
}

export function bindBoardFeature() {
  const els = boardElements();
  els.boardCreatePost.addEventListener("click", async () => {
    try {
      await createPost();
    } catch (error) {
      setBoardMessage(error.message, true);
    }
  });
  els.boardSavePost.addEventListener("click", async () => {
    try {
      await saveCurrentPost();
    } catch (error) {
      setBoardMessage(error.message, true);
    }
  });
  els.boardBackToList.addEventListener("click", async () => {
    await closeEditor();
  });
  els.boardSearch.addEventListener(
    "input",
    debounce(async () => {
      try {
        await refreshBoardPosts();
      } catch (error) {
        setBoardMessage(error.message, true);
      }
    }, 180)
  );
}

export async function initializeBoard() {
  showBoardScreen();
  await refreshBoardPosts();
}
