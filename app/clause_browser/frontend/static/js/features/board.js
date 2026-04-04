import {
  applyWorkspaceSnapshot,
  abortActiveRequests,
  clearMessage,
  clearTransientActivityUi,
  clearSelectionNoteUiState,
  state,
  getBoardScope,
  getWorkspaceSnapshot,
  openNoticeModal,
  resetWorkspace,
  setBoardScope,
} from "../core.js";
import {
  clearBoardEditorSession,
  readBoardEditorSession,
  shouldPreferSessionWorkspace,
  writeBoardEditorSession,
} from "../utils/board-session.js";

const EDITOR_ID_KEY = "specbot-board-editor-id-v1";
const EDITOR_LABEL_KEY = "specbot-board-editor-label-v1";
const HEARTBEAT_INTERVAL_MS = 30_000;
const VIEW_AUTOSAVE_DEBOUNCE_MS = 800;
const BOARD_MESSAGE_HIDE_DELAY_MS = 3000;

const boardState = {
  currentPostId: "",
  currentLock: null,
  boards: [],
  currentBoardId: "default",
  heartbeatId: 0,
  mode: "list",
  deleteTarget: null,
  createScopeDraft: {
    releaseData: "",
    release: "",
  },
  isDraft: false,
  isRestoringRoute: false,
  autosaveTimerId: 0,
  messageTimerId: 0,
};

const BOARD_ROUTE_PARAM = "board";
const BOARD_POST_PARAM = "post";

function editorId() {
  const existing = window.sessionStorage.getItem(EDITOR_ID_KEY);
  if (existing) {
    return existing;
  }
  const next = typeof crypto !== "undefined" && crypto.randomUUID ? crypto.randomUUID() : `editor-${Date.now()}`;
  window.sessionStorage.setItem(EDITOR_ID_KEY, next);
  return next;
}

function editorLabel() {
  const existing = window.sessionStorage.getItem(EDITOR_LABEL_KEY);
  if (existing) {
    return existing;
  }
  const label = `Editor ${editorId().slice(0, 8)}`;
  window.sessionStorage.setItem(EDITOR_LABEL_KEY, label);
  return label;
}

function boardElements() {
  return {
    boardScreen: document.getElementById("board-screen"),
    editorScreen: document.getElementById("editor-screen"),
    boardSearch: document.getElementById("board-search"),
    boardSelect: document.getElementById("board-select"),
    boardCreateBoard: document.getElementById("board-create-board"),
    boardDeleteBoard: document.getElementById("board-delete-board"),
    boardCreatePost: document.getElementById("board-create-post"),
    boardListCount: document.getElementById("board-list-count"),
    boardMessageBar: document.getElementById("board-message-bar"),
    boardPostList: document.getElementById("board-post-list"),
    boardCreateModal: document.getElementById("board-create-modal"),
    boardCreateReleaseData: document.getElementById("board-create-release-data"),
    boardCreateRelease: document.getElementById("board-create-release"),
    boardCreateConfirm: document.getElementById("board-create-confirm"),
    boardCreateBoardModal: document.getElementById("board-create-board-modal"),
    boardCreateBoardName: document.getElementById("board-create-board-name"),
    boardCreateBoardConfirm: document.getElementById("board-create-board-confirm"),
    boardBackToList: document.getElementById("board-back-to-list"),
    boardSavePost: document.getElementById("board-save-post"),
    boardPostTitle: document.getElementById("board-post-title"),
    boardReleaseData: document.getElementById("board-release-data"),
    boardRelease: document.getElementById("board-release"),
    openPickerButton: document.getElementById("open-picker-button"),
    exportButton: document.getElementById("export-button"),
    boardDeleteModal: document.getElementById("board-delete-modal"),
    boardDeleteModalText: document.getElementById("board-delete-modal-text"),
    boardDeleteCancel: document.getElementById("board-delete-cancel"),
    boardDeleteConfirm: document.getElementById("board-delete-confirm"),
  };
}

function setBoardMessage(text, isError = false) {
  const el = boardElements().boardMessageBar;
  el.innerHTML = text ? `<div class="message ${isError ? "error" : ""}">${escapeHtml(text)}</div>` : "";
  if (boardState.messageTimerId) {
    window.clearTimeout(boardState.messageTimerId);
    boardState.messageTimerId = 0;
  }
  if (text && !isError) {
    boardState.messageTimerId = window.setTimeout(() => {
      setBoardMessage("", false);
    }, BOARD_MESSAGE_HIDE_DELAY_MS);
  }
}

function currentBoard() {
  return boardState.boards.find((item) => item.boardId === boardState.currentBoardId) || null;
}

function isLockedByAnotherEditor(lock = boardState.currentLock) {
  return Boolean(lock && String(lock.editorId || "").trim() && String(lock.editorId || "").trim() !== editorId());
}

function renderBoardSelector() {
  const els = boardElements();
  if (!els.boardSelect) {
    return;
  }
  const boards = boardState.boards || [];
  if (!boards.length) {
    els.boardSelect.innerHTML = "";
    return;
  }
  if (!boards.some((item) => item.boardId === boardState.currentBoardId)) {
    boardState.currentBoardId = boards[0].boardId || "default";
  }
  els.boardSelect.innerHTML = boards
    .map(
      (item) =>
        `<option value="${escapeHtml(item.boardId)}" ${item.boardId === boardState.currentBoardId ? "selected" : ""}>${escapeHtml(item.name || item.boardId)}</option>`
    )
    .join("");
  if (els.boardDeleteBoard) {
    els.boardDeleteBoard.classList.toggle("hidden", boardState.currentBoardId === "default");
  }
}

function showBoardError(error) {
  const message = String(error?.message || error || "Request failed");
  if (/already being edited/i.test(message)) {
    openNoticeModal(message);
    return;
  }
  setBoardMessage(message, true);
}

function showBoardScreen() {
  boardState.mode = "list";
  boardState.isDraft = false;
  document.body.dataset.boardMode = "list";
  document.body.dataset.boardPostId = "";
  boardElements().boardScreen.classList.remove("hidden");
  boardElements().editorScreen.classList.add("hidden");
}

function showEditorScreen() {
  boardElements().boardScreen.classList.add("hidden");
  boardElements().editorScreen.classList.remove("hidden");
}

function applyEditorMode(mode) {
  boardState.mode = mode;
  document.body.dataset.boardMode = mode;
  const els = boardElements();
  const isEdit = mode === "edit";
  const isView = mode === "view";
  els.boardSavePost.classList.toggle("hidden", !isEdit);
  els.exportButton.classList.toggle("hidden", !isView);
  els.boardPostTitle.readOnly = !isEdit;
  const scopeLocked = true;
  els.boardReleaseData.disabled = scopeLocked;
  els.boardRelease.disabled = scopeLocked;
  if (els.openPickerButton) {
    els.openPickerButton.classList.toggle("hidden", isView);
  }
}

function availableReleaseScopes() {
  return Array.isArray(state.config?.releaseScopes) ? state.config.releaseScopes : [];
}

function buildScopeOptionState(scope = getBoardScope()) {
  const scopes = availableReleaseScopes();
  const releaseDataValues = [...new Set(scopes.map((item) => String(item.releaseData || "").trim()).filter(Boolean))].sort();
  const selectedReleaseData = String(scope.releaseData || releaseDataValues[0] || "").trim();
  const releaseValues = [
    ...new Set(
      scopes
        .filter((item) => String(item.releaseData || "").trim() === selectedReleaseData)
        .map((item) => String(item.release || "").trim())
        .filter(Boolean)
    ),
  ].sort();
  const selectedRelease = String(scope.release || releaseValues[0] || "").trim();
  return {
    releaseDataValues,
    selectedReleaseData,
    releaseValues,
    selectedRelease,
  };
}

function renderScopeSelects(releaseDataEl, releaseEl, scope = getBoardScope(), { persist = false } = {}) {
  const { releaseDataValues, selectedReleaseData, releaseValues, selectedRelease } = buildScopeOptionState(scope);
  releaseDataEl.innerHTML = releaseDataValues
    .map((value) => `<option value="${escapeHtml(value)}" ${value === selectedReleaseData ? "selected" : ""}>${escapeHtml(value)}</option>`)
    .join("");
  releaseEl.innerHTML = releaseValues
    .map((value) => `<option value="${escapeHtml(value)}" ${value === selectedRelease ? "selected" : ""}>${escapeHtml(value)}</option>`)
    .join("");
  if (persist) {
    setBoardScope({ releaseData: selectedReleaseData, release: selectedRelease });
  }
  return { releaseData: selectedReleaseData, release: selectedRelease };
}

function renderBoardScopeOptions(scope = getBoardScope()) {
  const { boardReleaseData, boardRelease } = boardElements();
  renderScopeSelects(boardReleaseData, boardRelease, scope, { persist: true });
}

function openCreateModal() {
  const els = boardElements();
  boardState.createScopeDraft = renderScopeSelects(
    els.boardCreateReleaseData,
    els.boardCreateRelease,
    getBoardScope(),
    { persist: false }
  );
  els.boardCreateModal.classList.remove("hidden");
  els.boardCreateModal.setAttribute("aria-hidden", "false");
}

function closeCreateModal() {
  const { boardCreateModal } = boardElements();
  boardCreateModal.classList.add("hidden");
  boardCreateModal.setAttribute("aria-hidden", "true");
}

function updateCreateScopeDraft() {
  const els = boardElements();
  boardState.createScopeDraft = renderScopeSelects(
    els.boardCreateReleaseData,
    els.boardCreateRelease,
    {
      releaseData: els.boardCreateReleaseData.value,
      release: els.boardCreateRelease.value,
    },
    { persist: false }
  );
}

async function confirmCreatePost() {
  const scope = boardState.createScopeDraft;
  if (!scope.releaseData || !scope.release) {
    throw new Error("게시글의 Spec Date와 Release를 선택하세요.");
  }
  setBoardScope(scope);
  closeCreateModal();
  await openDraftPost();
}

function openCreateBoardModal() {
  const els = boardElements();
  els.boardCreateBoardName.value = "";
  els.boardCreateBoardModal.classList.remove("hidden");
  els.boardCreateBoardModal.setAttribute("aria-hidden", "false");
}

function closeCreateBoardModal() {
  const els = boardElements();
  els.boardCreateBoardModal.classList.add("hidden");
  els.boardCreateBoardModal.setAttribute("aria-hidden", "true");
}

async function confirmCreateBoard() {
  const els = boardElements();
  const name = els.boardCreateBoardName.value.trim();
  if (!name) {
    throw new Error("게시판 이름을 입력하세요.");
  }
  const data = await request(`/api/clause-browser/board/boards`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  boardState.currentBoardId = data.boardId || boardState.currentBoardId;
  closeCreateBoardModal();
  await refreshBoards();
  await refreshBoardPosts();
}

async function deleteCurrentBoard() {
  const board = currentBoard();
  if (!board || board.boardId === "default") {
    throw new Error("기본 게시판은 삭제할 수 없습니다.");
  }
  await request(`/api/clause-browser/board/boards/${board.boardId}/delete`, {
    method: "POST",
  });
  boardState.currentBoardId = "default";
  await refreshBoards();
  await refreshBoardPosts();
  setBoardMessage("게시판을 삭제했습니다.", false);
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

async function refreshBoards() {
  const data = await request(`/api/clause-browser/board/boards`);
  boardState.boards = Array.isArray(data.items) ? data.items : [];
  renderBoardSelector();
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
        <article class="board-post-card" data-action="view-post" data-post-id="${escapeHtml(item.postId)}" tabindex="0" role="button">
          <div class="board-post-main">
            <div class="board-post-title">${escapeHtml(item.title || "Untitled post")}</div>
            <div class="board-post-meta">
              <span>${escapeHtml(item.createdAt || "")}</span>
              <span>${escapeHtml(currentBoard()?.name || "")}</span>
              <span>${escapeHtml([item.releaseData, item.release].filter(Boolean).join(" / "))}</span>
              <span>${escapeHtml(lockText)}</span>
            </div>
          </div>
          <div class="board-post-actions">
            <button class="primary" data-action="edit-post" data-post-id="${escapeHtml(item.postId)}">편집</button>
            <button class="danger" data-action="delete-post" data-post-id="${escapeHtml(item.postId)}" data-post-title="${escapeHtml(item.title || "Untitled post")}">삭제</button>
          </div>
        </article>
      `;
    })
    .join("");
  boardPostList.querySelectorAll("[data-action='view-post']").forEach((card) => {
    const open = async () => {
      try {
        await openExistingPostReadOnly(card.dataset.postId || "");
      } catch (error) {
        showBoardError(error);
      }
    };
    card.addEventListener("click", async (event) => {
      const target = event.target;
      if (target instanceof Element && target.closest("button")) {
        return;
      }
      await open();
    });
    card.addEventListener("keydown", async (event) => {
      if (event.key !== "Enter" && event.key !== " ") {
        return;
      }
      event.preventDefault();
      await open();
    });
  });
  boardPostList.querySelectorAll("[data-action='edit-post']").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        await openExistingPost(button.dataset.postId || "");
      } catch (error) {
        showBoardError(error);
      }
    });
  });
  boardPostList.querySelectorAll("[data-action='delete-post']").forEach((button) => {
    button.addEventListener("click", () => {
      openDeleteModal({
        postId: button.dataset.postId || "",
        title: button.dataset.postTitle || "Untitled post",
      });
    });
  });
}

async function refreshBoardPosts() {
  const query = encodeURIComponent(boardElements().boardSearch.value.trim());
  const boardId = encodeURIComponent(boardState.currentBoardId || "default");
  const data = await request(`/api/clause-browser/board/posts?query=${query}&boardId=${boardId}`);
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

function clearAutosaveTimer() {
  if (boardState.autosaveTimerId) {
    window.clearTimeout(boardState.autosaveTimerId);
    boardState.autosaveTimerId = 0;
  }
}

function releaseCurrentLockOnUnload() {
  if (!boardState.currentPostId || !boardState.currentLock) {
    return;
  }
  const payload = JSON.stringify({
    editorId: editorId(),
    editorLabel: editorLabel(),
  });
  const url = `/api/clause-browser/board/posts/${boardState.currentPostId}/lock/release`;
  try {
    if (navigator.sendBeacon) {
      const blob = new Blob([payload], { type: "application/json" });
      navigator.sendBeacon(url, blob);
    } else {
      fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: payload,
        keepalive: true,
      }).catch(() => {});
    }
  } catch (_error) {
    // ignore unload release errors
  }
}

async function createPost() {
  openCreateModal();
}

async function openExistingPost(postId, options = {}) {
  await request(`/api/clause-browser/board/posts/${postId}/lock/acquire`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ editorId: editorId(), editorLabel: editorLabel() }),
  });
  const data = await request(`/api/clause-browser/board/posts/${postId}`);
  await openPostInEditor(data, options);
}

async function openExistingPostReadOnly(postId, options = {}) {
  const data = await request(`/api/clause-browser/board/posts/${postId}`);
  await openPostInViewer(data, options);
}

async function openDraftPost(options = {}) {
  abortActiveRequests();
  clearMessage();
  clearTransientActivityUi();
  clearSelectionNoteUiState();
  clearAutosaveTimer();
  boardState.currentPostId = "";
  boardState.currentLock = null;
  boardState.isDraft = true;
  document.body.dataset.boardPostId = "";
  if (!boardState.currentBoardId) {
    boardState.currentBoardId = "default";
  }
  boardElements().boardPostTitle.value = "새 게시글";
  renderBoardScopeOptions(getBoardScope());
  showEditorScreen();
  applyEditorMode("edit");
  stopHeartbeat();
  writeBoardEditorSession({ postId: "", mode: "draft" });
  await resetWorkspace();
  navigateBoard("draft", { replace: options.replace === true });
}

async function openPostInEditor(post, options = {}) {
  abortActiveRequests();
  clearMessage();
  clearTransientActivityUi();
  clearSelectionNoteUiState();
  clearAutosaveTimer();
  boardState.currentPostId = post.postId;
  boardState.currentLock = post.lock || null;
  document.body.dataset.boardPostId = post.postId || "";
  boardState.currentBoardId = post.boardId || boardState.currentBoardId || "default";
  renderBoardSelector();
  boardState.isDraft = false;
  const sessionSnapshot = getWorkspaceSnapshot();
  const session = readBoardEditorSession();
  const preferredWorkspaceState = shouldPreferSessionWorkspace(session, post.postId, "edit")
    ? sessionSnapshot
    : (post.workspaceState || {});
  boardElements().boardPostTitle.value = post.title || "";
  renderBoardScopeOptions({ releaseData: post.releaseData, release: post.release });
  showEditorScreen();
  applyEditorMode("edit");
  await resetWorkspace();
  await applyWorkspaceSnapshot({
    ...preferredWorkspaceState,
    boardScope: { releaseData: post.releaseData, release: post.release },
  });
  writeBoardEditorSession({ postId: post.postId, mode: "edit" });
  startHeartbeat();
  navigateBoard("edit", { postId: post.postId, replace: options.replace === true });
}

async function openPostInViewer(post, options = {}) {
  abortActiveRequests();
  clearMessage();
  clearTransientActivityUi();
  clearSelectionNoteUiState();
  clearAutosaveTimer();
  boardState.currentPostId = post.postId;
  boardState.currentLock = post.lock || null;
  document.body.dataset.boardPostId = post.postId || "";
  boardState.currentBoardId = post.boardId || boardState.currentBoardId || "default";
  renderBoardSelector();
  boardState.isDraft = false;
  boardElements().boardPostTitle.value = post.title || "";
  renderBoardScopeOptions({ releaseData: post.releaseData, release: post.release });
  showEditorScreen();
  applyEditorMode("view");
  stopHeartbeat();
  await resetWorkspace();
  await applyWorkspaceSnapshot({
    ...(post.workspaceState || {}),
    boardScope: { releaseData: post.releaseData, release: post.release },
  });
  writeBoardEditorSession({ postId: post.postId, mode: "view" });
  navigateBoard("view", { postId: post.postId, replace: options.replace === true });
}

async function saveCurrentPost() {
  await persistCurrentPost();
  setBoardMessage("게시글을 저장했습니다.", false);
  await closeEditor();
}

async function persistCurrentPost({ autosave = false } = {}) {
  if (autosave && boardState.mode === "view" && isLockedByAnotherEditor()) {
    return;
  }
  const scope = getBoardScope();
  if (!scope.releaseData || !scope.release) {
    throw new Error("게시글의 Spec Date와 Release를 선택하세요.");
  }
  const payload = {
    editorId: editorId(),
    editorLabel: editorLabel(),
    boardId: boardState.currentBoardId || "default",
    title: boardElements().boardPostTitle.value.trim() || "Untitled post",
    body: "",
    releaseData: scope.releaseData,
    release: scope.release,
    workspaceState: getWorkspaceSnapshot(),
  };
  if (!boardState.currentPostId) {
    if (!boardState.isDraft) {
      throw new Error("현재 게시글 ID를 찾을 수 없습니다. 새 글 생성이 아니라 기존 글 업데이트를 기대한 상태입니다.");
    }
    const data = await request(`/api/clause-browser/board/posts`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    boardState.currentPostId = data.postId || "";
    boardState.currentLock = data.lock || null;
    boardState.isDraft = false;
  } else {
    const data = await request(`/api/clause-browser/board/posts/${boardState.currentPostId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    boardState.currentLock = data.lock || null;
  }
  if (boardState.currentLock) {
    startHeartbeat();
  }
  if (!autosave) {
    setBoardMessage("게시글을 저장했습니다.", false);
  }
}

function scheduleViewAutosave() {
  if (boardState.mode !== "view" || !boardState.currentPostId || boardState.isRestoringRoute) {
    return;
  }
  if (isLockedByAnotherEditor()) {
    return;
  }
  clearAutosaveTimer();
  boardState.autosaveTimerId = window.setTimeout(async () => {
    boardState.autosaveTimerId = 0;
    if (boardState.mode !== "view" || !boardState.currentPostId || boardState.isDraft || boardState.isRestoringRoute) {
      return;
    }
    if (isLockedByAnotherEditor()) {
      return;
    }
    try {
      await persistCurrentPost({ autosave: true });
    } catch (error) {
      showBoardError(error);
    }
  }, VIEW_AUTOSAVE_DEBOUNCE_MS);
}

function openDeleteModal(target) {
  boardState.deleteTarget = target;
  const els = boardElements();
  els.boardDeleteModalText.textContent = `"${target.title}" 게시글을 정말 삭제할까요?`;
  els.boardDeleteModal.classList.remove("hidden");
  els.boardDeleteModal.setAttribute("aria-hidden", "false");
}

function closeDeleteModal() {
  const els = boardElements();
  boardState.deleteTarget = null;
  els.boardDeleteModal.classList.add("hidden");
  els.boardDeleteModal.setAttribute("aria-hidden", "true");
}

async function deletePost(postId) {
  await request(`/api/clause-browser/board/posts/${postId}/delete`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ editorId: editorId(), editorLabel: editorLabel() }),
  });
  if (boardState.currentPostId === postId) {
    stopHeartbeat();
    boardState.currentPostId = "";
    boardState.currentLock = null;
    clearBoardEditorSession();
    await resetWorkspace();
    showBoardScreen();
  }
  setBoardMessage("게시글을 삭제했습니다.", false);
  await refreshBoardPosts();
}

async function closeEditor() {
  abortActiveRequests();
  clearMessage();
  clearTransientActivityUi();
  clearSelectionNoteUiState();
  clearAutosaveTimer();
  stopHeartbeat();
  if (boardState.currentPostId && boardState.currentLock) {
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
  boardState.isDraft = false;
  document.body.dataset.boardPostId = "";
  clearBoardEditorSession();
  showBoardScreen();
  navigateBoard("list");
  await refreshBoardPosts();
}

function buildBoardUrl(mode, postId = "") {
  const url = new URL(window.location.href);
  if (mode === "list") {
    url.searchParams.delete(BOARD_ROUTE_PARAM);
    url.searchParams.delete(BOARD_POST_PARAM);
    return `${url.pathname}${url.search}${url.hash}`;
  }
  url.searchParams.set(BOARD_ROUTE_PARAM, mode);
  if (postId) {
    url.searchParams.set(BOARD_POST_PARAM, postId);
  } else {
    url.searchParams.delete(BOARD_POST_PARAM);
  }
  return `${url.pathname}${url.search}${url.hash}`;
}

function navigateBoard(mode, { postId = "", replace = false } = {}) {
  if (boardState.isRestoringRoute) {
    return;
  }
  const url = buildBoardUrl(mode, postId);
  const method = replace ? "replaceState" : "pushState";
  window.history[method]({ boardMode: mode, postId }, "", url);
}

async function restoreBoardRoute() {
  const url = new URL(window.location.href);
  const mode = url.searchParams.get(BOARD_ROUTE_PARAM) || "list";
  const postId = url.searchParams.get(BOARD_POST_PARAM) || "";
  boardState.isRestoringRoute = true;
  try {
    const shouldReleaseCurrentLock =
      Boolean(boardState.currentPostId && boardState.currentLock) &&
      (mode !== "edit" || postId !== boardState.currentPostId);
    if (shouldReleaseCurrentLock) {
      await closeEditor();
    }
    if (mode === "draft") {
      await openDraftPost({ replace: true });
      return;
    }
    if (mode === "edit" && postId) {
      await openExistingPost(postId, { replace: true });
      return;
    }
    if (mode === "view" && postId) {
      await openExistingPostReadOnly(postId, { replace: true });
      return;
    }
    await closeEditor();
  } finally {
    boardState.isRestoringRoute = false;
  }
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
  window.addEventListener("pagehide", releaseCurrentLockOnUnload);
  window.addEventListener("beforeunload", releaseCurrentLockOnUnload);
  window.addEventListener("specbot:workspace-persisted", () => {
    scheduleViewAutosave();
  });
  window.addEventListener("popstate", async () => {
    try {
      await restoreBoardRoute();
    } catch (error) {
      showBoardError(error);
    }
  });
  document.querySelectorAll("[data-action='close-board-delete-modal']").forEach((element) => {
    element.addEventListener("click", () => closeDeleteModal());
  });
  document.querySelectorAll("[data-action='close-board-create-modal']").forEach((element) => {
    element.addEventListener("click", () => closeCreateModal());
  });
  document.querySelectorAll("[data-action='close-board-create-board-modal']").forEach((element) => {
    element.addEventListener("click", () => closeCreateBoardModal());
  });
  els.boardSelect.addEventListener("change", async () => {
    boardState.currentBoardId = els.boardSelect.value || "default";
    renderBoardSelector();
    try {
      await refreshBoardPosts();
    } catch (error) {
      showBoardError(error);
    }
  });
  els.boardCreateBoard.addEventListener("click", () => {
    openCreateBoardModal();
  });
  els.boardDeleteBoard.addEventListener("click", async () => {
    try {
      await deleteCurrentBoard();
    } catch (error) {
      showBoardError(error);
    }
  });
  els.boardCreatePost.addEventListener("click", async () => {
    try {
      await createPost();
    } catch (error) {
      showBoardError(error);
    }
  });
  els.boardSavePost.addEventListener("click", async () => {
    try {
      await saveCurrentPost();
    } catch (error) {
      showBoardError(error);
    }
  });
  els.boardBackToList.addEventListener("click", async () => {
    await closeEditor();
  });
  els.boardDeleteCancel.addEventListener("click", () => {
    closeDeleteModal();
  });
  els.boardDeleteConfirm.addEventListener("click", async () => {
    const target = boardState.deleteTarget;
    if (!target?.postId) {
      closeDeleteModal();
      return;
    }
    try {
      await deletePost(target.postId);
      closeDeleteModal();
    } catch (error) {
      closeDeleteModal();
      showBoardError(error);
    }
  });
  els.boardCreateConfirm.addEventListener("click", async () => {
    try {
      await confirmCreatePost();
    } catch (error) {
      showBoardError(error);
    }
  });
  els.boardCreateBoardConfirm.addEventListener("click", async () => {
    try {
      await confirmCreateBoard();
    } catch (error) {
      showBoardError(error);
    }
  });
  els.boardSearch.addEventListener(
    "input",
    debounce(async () => {
      try {
        await refreshBoardPosts();
      } catch (error) {
        showBoardError(error);
      }
    }, 180)
  );
  els.boardCreateReleaseData.addEventListener("change", () => {
    updateCreateScopeDraft();
  });
  els.boardCreateRelease.addEventListener("change", () => {
    boardState.createScopeDraft = {
      releaseData: els.boardCreateReleaseData.value,
      release: els.boardCreateRelease.value,
    };
  });
}

export async function initializeBoard() {
  renderBoardScopeOptions();
  showBoardScreen();
  await refreshBoards();
  await refreshBoardPosts();
  await restoreBoardRoute();
}
