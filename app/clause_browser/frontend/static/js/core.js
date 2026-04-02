import { destroyClauseEditorsIn } from "./vendor/tinymce-editor.js";
import { initializeClauseEditors } from "./features/editor.js";
import {
  createStableBlockId,
  createStableCellId,
  normalizeEditorText,
  ensureBlocksHaveStableIds,
  ensureNodeStableBlockIds,
  ensureForestStableBlockIds,
  deriveNodeTextFromBlocks,
  removeBlockAt,
} from "./utils/block-utils.js";
import {
  removeTableRow,
  removeTableColumn,
  removeTableRowFromCells,
  removeTableColumnFromCells,
} from "./utils/table-utils.js";

const state = {
  config: null,
  documents: [],
  activeSpecNo: "",
  loadedRoots: [],
  clauseCatalogBySpec: {},
  ui: {
    isPickerOpen: false,
    isSpecbotSettingsOpen: false,
    expandedKeys: new Set(),
    focusedKey: "",
    viewportKey: "",
    collapsedSpecs: new Set(),
    collapsedLoadedSpecs: new Set(),
    message: null,
    clauseQuery: "",
    specbotQueryText: "",
    specbotSettings: {},
    boardScope: {
      releaseData: "",
      release: "",
    },
    specbotResults: [],
    specbotQueryStatus: "",
    specbotDocumentSettingsLoading: false,
    notes: [],
    highlights: [],
    busy: null,
    translationJob: null,
    translationTask: null,
    clauseNoteModalKey: "",
    selection: {
      text: "",
      clauseKey: "",
      clauseLabel: "",
      blockId: "",
      blockIndex: -1,
      rowIndex: -1,
      cellIndex: -1,
      cellId: "",
      rowText: "",
      hasSelection: false,
    },
    nodeMenu: {
      key: "",
      x: 0,
      y: 0,
    },
  },
};

const elements = {};
const SESSION_STORAGE_KEY = "specbot-clause-browser-state-v7";
const TRANSLATION_CHUNK_LIMIT = 12000;
const SPECBOT_QUERY_BUSY_LABEL = "SpecBot query 수행 중입니다.";
const DOCUMENT_SEARCH_BUSY_LABEL = "문서 검색 중입니다.";
const DOCUMENT_SELECT_BUSY_LABEL = "문서를 불러오는 중입니다.";
const activeRequestControllers = new Set();
const activeLocalWorkSlots = new Set();
const LOCAL_WORK_SLOT_LIMIT = 7;
const LOCAL_WORK_SLOT_TTL_MS = 10 * 60 * 1000;
const LOCAL_WORK_LOCK_TTL_MS = 2000;
const LOCAL_WORK_STATE_KEY = "specbot-work-slots-v1";
const LOCAL_WORK_LOCK_KEY = "specbot-work-slots-lock-v1";
const LOCAL_WORK_TAB_ID = typeof crypto !== "undefined" && crypto.randomUUID ? crypto.randomUUID() : `tab-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
const SESSION_PERSIST_DEBOUNCE_MS = 120;
const TRANSIENT_STATUS_HIDE_DELAY_MS = 2000;
let sessionPersistTimer = 0;
let messageHideTimer = 0;

function bindElements() {
  elements.openPickerButton = document.getElementById("open-picker-button");
  elements.specbotQuery = document.getElementById("specbot-query");
  elements.specbotDepthOptions = [...document.querySelectorAll("input[name='specbot-depth']")];
  elements.specbotSpinner = document.getElementById("specbot-spinner");
  elements.runSpecbotLabel = document.getElementById("run-specbot-label");
  elements.specbotQueryStatus = document.getElementById("specbot-query-status");
  elements.openSpecbotSettings = document.getElementById("open-specbot-settings");
  elements.specbotResultList = document.getElementById("specbot-result-list");
  elements.clearSpecbotResults = document.getElementById("clear-specbot-results");
  elements.pickerSelectionSummary = document.getElementById("picker-selection-summary");
  elements.selectedClauseCount = document.getElementById("selected-clause-count");
  elements.selectedClauseList = document.getElementById("selected-clause-list");
  elements.pickerModal = document.getElementById("clause-picker-modal");
  elements.pickerTitle = document.getElementById("picker-title");
  elements.documentSearch = document.getElementById("document-search");
  elements.documentList = document.getElementById("document-list");
  elements.documentCount = document.getElementById("document-count");
  elements.activeDocumentLabel = document.getElementById("active-document-label");
  elements.clauseSearch = document.getElementById("clause-search");
  elements.clauseTreeList = document.getElementById("clause-tree-list");
  elements.treeContainer = document.getElementById("tree-container");
  elements.loadedSummary = document.getElementById("loaded-summary");
  elements.messageBar = document.getElementById("message-bar");
  elements.translationStatus = document.getElementById("translation-status");
  elements.exportTitle = document.getElementById("export-title");
  elements.exportButton = document.getElementById("export-button");
  elements.selectionMenu = document.getElementById("selection-menu");
  elements.nodeMenu = document.getElementById("node-menu");
  elements.nodeMenuAddParent = document.getElementById("node-menu-add-parent");
  elements.specbotSettingsModal = document.getElementById("specbot-settings-modal");
  elements.noticeModal = document.getElementById("notice-modal");
  elements.noticeModalText = document.getElementById("notice-modal-text");
  elements.clauseNoteModal = document.getElementById("clause-note-modal");
  elements.clauseNoteModalTitle = document.getElementById("clause-note-modal-title");
  elements.clauseNoteModalBody = document.getElementById("clause-note-modal-body");
  elements.settingBaseUrl = document.getElementById("setting-base-url");
  elements.settingConfigBaseUrl = document.getElementById("setting-config-base-url");
  elements.settingLimit = document.getElementById("setting-limit");
  elements.settingIterations = document.getElementById("setting-iterations");
  elements.settingNextIterationLimit = document.getElementById("setting-next-iteration-limit");
  elements.settingFollowupMode = document.getElementById("setting-followup-mode");
  elements.settingSummary = document.getElementById("setting-summary");
  elements.settingRegistry = document.getElementById("setting-registry");
  elements.settingLocalModelDir = document.getElementById("setting-local-model-dir");
  elements.settingDevice = document.getElementById("setting-device");
  elements.settingSparseBoost = document.getElementById("setting-sparse-boost");
  elements.settingVectorBoost = document.getElementById("setting-vector-boost");
  elements.settingDocumentSelectionCount = document.getElementById("setting-document-selection-count");
  elements.settingSelectAllDocuments = document.getElementById("setting-select-all-documents");
  elements.settingClearAllDocuments = document.getElementById("setting-clear-all-documents");
  elements.settingDocumentList = document.getElementById("setting-document-list");
  elements.settingRejectedClauseList = document.getElementById("setting-rejected-clause-list");
  elements.settingClearRejectedClauses = document.getElementById("setting-clear-rejected-clauses");
  elements.settingExcludeSpecs = document.getElementById("setting-exclude-specs");
  elements.settingExcludeClauses = document.getElementById("setting-exclude-clauses");
  elements.saveSpecbotSettings = document.getElementById("save-specbot-settings");

  [elements.specbotQueryStatus, elements.translationStatus, elements.messageBar].forEach((element) => {
    if (element && element.parentElement !== document.body) {
      document.body.appendChild(element);
    }
  });
}

function bindGlobalEvents() {
  elements.treeContainer.addEventListener("scroll", debounce(syncViewportSelection, 40));
  document.addEventListener("keydown", handleTreeDeleteKeydown);
  document.addEventListener("click", (event) => {
    if (!elements.selectionMenu.contains(event.target)) {
      hideSelectionMenu();
    }
    if (!elements.nodeMenu.contains(event.target)) {
      hideNodeMenu();
    }
    if (event.target.closest("[data-action='close-picker']")) {
      closePicker();
    }
    if (event.target.closest("[data-action='close-specbot-settings']")) {
      closeSpecbotSettings();
    }
    if (event.target.closest("[data-action='close-notice-modal']")) {
      closeNoticeModal();
    }
    if (event.target.closest("[data-action='close-clause-note-modal']")) {
      closeClauseNoteModal();
    }
  });
  window.addEventListener("pagehide", () => {
    flushPersistSessionState();
    abortActiveRequests();
  });
  window.addEventListener("beforeunload", () => {
    flushPersistSessionState();
    abortActiveRequests();
  });
}

async function loadConfig() {
  const response = await apiGet("/api/clause-browser/config");
  state.config = response.data;
  state.ui.specbotSettings = { ...response.data.specbotDefaults };
  applySpecbotSettingsToForm();
}

function getBoardScope() {
  return {
    releaseData: String(state.ui.boardScope?.releaseData || "").trim(),
    release: String(state.ui.boardScope?.release || "").trim(),
  };
}

function setBoardScope(scope = {}) {
  const nextScope = {
    releaseData: String(scope.releaseData || "").trim(),
    release: String(scope.release || "").trim(),
  };
  const previousScope = getBoardScope();
  const scopeChanged =
    previousScope.releaseData !== nextScope.releaseData || previousScope.release !== nextScope.release;
  state.ui.boardScope = nextScope;
  if (scopeChanged) {
    state.documents = [];
    state.activeSpecNo = "";
    state.clauseCatalogBySpec = {};
    if (elements.activeDocumentLabel) {
      elements.activeDocumentLabel.textContent = "문서를 선택하세요";
    }
  }
  persistSessionState();
}

async function refreshDocuments(options = {}) {
  if (!beginBusy("문서 검색 중입니다.", { ...options, allowDuringSpecbotQuery: true })) {
    return;
  }
  if (options.forSpecbotSettings) {
    state.ui.specbotDocumentSettingsLoading = true;
    if (state.ui.isSpecbotSettingsOpen) {
      renderSpecbotDocumentSettings();
    }
  }
  const query = encodeURIComponent(elements.documentSearch.value.trim());
  const clauseQuery = encodeURIComponent((elements.clauseSearch?.value || "").trim());
  const scope = getBoardScope();
  const releaseData = encodeURIComponent(scope.releaseData);
  const release = encodeURIComponent(scope.release);
  try {
    const response = await apiGet(
      `/api/clause-browser/documents?query=${query}&clauseQuery=${clauseQuery}&releaseData=${releaseData}&release=${release}`
    );
    state.documents = response.data.items;
    renderDocuments();
    if (state.ui.isSpecbotSettingsOpen) {
      renderSpecbotDocumentSettings();
    }
  } finally {
    if (options.forSpecbotSettings) {
      state.ui.specbotDocumentSettingsLoading = false;
      if (state.ui.isSpecbotSettingsOpen) {
        renderSpecbotDocumentSettings();
      }
    }
    endBusy(options);
  }
}

async function openPicker() {
  await refreshDocuments({ silent: true, guard: false });
  state.ui.isPickerOpen = true;
  persistSessionState();
  elements.pickerModal.classList.remove("hidden");
  elements.pickerModal.setAttribute("aria-hidden", "false");
  elements.pickerTitle.textContent = state.activeSpecNo ? `${state.activeSpecNo} 문서 검색` : "문서 검색";
}

function closePicker() {
  state.ui.isPickerOpen = false;
  persistSessionState();
  elements.pickerModal.classList.add("hidden");
  elements.pickerModal.setAttribute("aria-hidden", "true");
}

async function openSpecbotSettings() {
  applySpecbotSettingsToForm();
  state.ui.isSpecbotSettingsOpen = true;
  state.ui.specbotDocumentSettingsLoading = true;
  renderSpecbotDocumentSettings();
  renderRejectedSpecbotClauses();
  persistSessionState();
  elements.specbotSettingsModal.classList.remove("hidden");
  elements.specbotSettingsModal.setAttribute("aria-hidden", "false");
  try {
    await refreshDocuments({ silent: true, forSpecbotSettings: true });
  } catch (error) {
    if (!isAbortedRequestError(error)) {
      setMessage(error.message, true);
    }
  }
}

function closeSpecbotSettings() {
  state.ui.isSpecbotSettingsOpen = false;
  state.ui.specbotDocumentSettingsLoading = false;
  persistSessionState();
  elements.specbotSettingsModal.classList.add("hidden");
  elements.specbotSettingsModal.setAttribute("aria-hidden", "true");
}

function openNoticeModal(text) {
  elements.noticeModalText.textContent = text;
  elements.noticeModal.classList.remove("hidden");
  elements.noticeModal.setAttribute("aria-hidden", "false");
}

function closeNoticeModal() {
  elements.noticeModal.classList.add("hidden");
  elements.noticeModal.setAttribute("aria-hidden", "true");
}

function openClauseNoteModal(clauseKey) {
  state.ui.clauseNoteModalKey = clauseKey;
  renderClauseNoteModal();
  persistSessionState();
  elements.clauseNoteModal.classList.remove("hidden");
  elements.clauseNoteModal.setAttribute("aria-hidden", "false");
}

function isBoardViewMode() {
  return document.body?.dataset?.boardMode === "view";
}

function isBoardEditMode() {
  return document.body?.dataset?.boardMode === "edit";
}

function closeClauseNoteModal() {
  state.ui.clauseNoteModalKey = "";
  persistSessionState();
  elements.clauseNoteModal.classList.add("hidden");
  elements.clauseNoteModal.setAttribute("aria-hidden", "true");
}

function renderClauseNoteModal() {
  const clauseKey = state.ui.clauseNoteModalKey;
  if (!clauseKey) {
    elements.clauseNoteModalBody.innerHTML = "";
    return;
  }
  const node = findNodeByKey(clauseKey);
  elements.clauseNoteModalTitle.textContent = node
    ? `${node.specNo} / ${node.clauseId} ${node.clauseTitle}`
    : "절 메모";
  const notes = getNotesForClause(clauseKey).filter((note) => note.type === "clause");
  const sourceText = node ? getClauseSourceText(node) : "";
  const note = notes[0] || null;
  elements.clauseNoteModalBody.innerHTML = `
    <section class="clause-note-modal-section">
      <div class="section-heading">
        <h3>원문</h3>
      </div>
      <label class="field">
        <textarea class="clause-note-source-textarea" rows="10" readonly>${escapeHtml(sourceText || "")}</textarea>
      </label>
    </section>
    <section class="clause-note-modal-section">
      <div class="section-heading">
        <h3>절 메모</h3>
        ${
          note
            ? `<button class="icon-button ghost note-delete-button" title="삭제" aria-label="삭제" data-action="delete-note" data-note-id="${escapeHtml(note.id)}">✕</button>`
            : ""
        }
      </div>
      ${
        note
          ? `
            <label class="field">
              <textarea class="clause-note-modal-textarea" data-action="edit-note-translation" data-note-id="${escapeHtml(note.id)}" rows="12" placeholder="번역 결과를 수정하세요.">${escapeHtml(
                note.translation || ""
              )}</textarea>
            </label>
          `
          : '<div class="muted">절 메모가 없습니다.</div>'
      }
    </section>
  `;
  bindClauseNoteModalEvents();
}

function bindClauseNoteModalEvents() {
  elements.clauseNoteModalBody.querySelectorAll("[data-action='edit-note-translation']").forEach((textarea) => {
    textarea.addEventListener("input", (event) => {
      updateNoteField(textarea.dataset.noteId || "", "translation", event.target.value);
    });
  });
  elements.clauseNoteModalBody.querySelectorAll("[data-action='delete-note']").forEach((button) => {
    button.addEventListener("click", () => {
      deleteNote(button.dataset.noteId || "");
    });
  });
}

function applySpecbotSettingsToForm() {
  const settings = state.ui.specbotSettings;
  elements.settingBaseUrl.value = settings.baseUrl || "";
  elements.settingConfigBaseUrl.value = settings.configBaseUrl || "";
  elements.settingLimit.value = settings.limit ?? 4;
  elements.settingIterations.value = settings.iterations ?? 1;
  elements.settingNextIterationLimit.value = settings.nextIterationLimit ?? 2;
  elements.settingFollowupMode.value = settings.followupMode || "sentence-summary";
  elements.settingSummary.value = settings.summary || "short";
  elements.settingRegistry.value = settings.registry || "";
  elements.settingLocalModelDir.value = settings.localModelDir || "";
  elements.settingDevice.value = settings.device || "cuda";
  elements.settingSparseBoost.value = settings.sparseBoost ?? 0;
  elements.settingVectorBoost.value = settings.vectorBoost ?? 1;
  elements.settingExcludeSpecs.value = Array.isArray(settings.excludeSpecs) ? settings.excludeSpecs.join("\n") : "";
  elements.settingExcludeClauses.value = Array.isArray(settings.excludeClauses)
    ? settings.excludeClauses.map((item) => `${item.specNo}:${item.clauseId}`).join("\n")
    : "";
  applySpecbotDepthSelection(getSpecbotDepthFromSettings(settings));
}

function saveSpecbotSettings() {
  const rejectedClauses = getRejectedSpecbotClauses();
  const queryDepth = getSelectedSpecbotDepth();
  state.ui.specbotSettings = {
    baseUrl: elements.settingBaseUrl.value.trim(),
    configBaseUrl: elements.settingConfigBaseUrl.value.trim(),
    limit: Number(elements.settingLimit.value),
    iterations: getIterationsForDepth(queryDepth),
    nextIterationLimit: Number(elements.settingNextIterationLimit.value),
    followupMode: elements.settingFollowupMode.value,
    summary: elements.settingSummary.value.trim(),
    registry: elements.settingRegistry.value.trim(),
    localModelDir: elements.settingLocalModelDir.value.trim(),
    device: elements.settingDevice.value.trim(),
    sparseBoost: Number(elements.settingSparseBoost.value),
    vectorBoost: Number(elements.settingVectorBoost.value),
    includedSpecs: getSelectedSpecbotDocuments(),
    excludeSpecs: parseSpecbotExcludeSpecs(elements.settingExcludeSpecs.value),
    excludeClauses: parseSpecbotExcludeClauses(elements.settingExcludeClauses.value),
    rejectedClauses,
    queryDepth,
  };
  pruneSpecbotResultsByCurrentExclusions();
  persistSessionState();
  renderSpecbotResults();
  closeSpecbotSettings();
}

function renderDocuments() {
  elements.documentCount.textContent = `${state.documents.length} docs`;
  if (!state.documents.length) {
    elements.documentList.innerHTML = '<div class="muted">일치하는 문서가 없습니다.</div>';
    return;
  }

  elements.documentList.innerHTML = state.documents
    .map((item) => {
      const activeClass = state.activeSpecNo === item.specNo ? "active" : "";
      return `
        <article class="list-card document-card ${activeClass}" data-spec-no="${escapeHtml(item.specNo)}" tabindex="0" role="button" aria-label="${escapeHtml(item.specNo)} 문서 선택">
          <h3>${escapeHtml(item.specNo)} <span class="muted">${escapeHtml(item.specTitle || "")}</span></h3>
          <div class="muted">${item.clauseCount} clauses · ${item.topLevelClauseCount} top-level</div>
        </article>
      `;
    })
    .join("");

  elements.documentList.querySelectorAll(".document-card").forEach((card) => {
    card.addEventListener("click", async () => {
      await selectDocument(card.dataset.specNo);
    });
    card.addEventListener("keydown", async (event) => {
      if (event.key !== "Enter" && event.key !== " ") {
        return;
      }
      event.preventDefault();
      await selectDocument(card.dataset.specNo);
    });
  });
}

async function selectDocument(specNo) {
  if (!beginBusy("문서를 불러오는 중입니다.", { allowDuringSpecbotQuery: true })) {
    return;
  }
  state.activeSpecNo = specNo;
  elements.activeDocumentLabel.textContent = specNo;
  elements.pickerTitle.textContent = `${specNo} 문서 검색`;
  persistSessionState();
  updateClauseTreeSummary();
  try {
    await ensureClauseCatalog(specNo);
    renderDocuments();
    renderClauseTree();
  } catch (error) {
    if (!isAbortedRequestError(error)) {
      setMessage(error.message, true);
    }
  } finally {
    endBusy({ allowDuringSpecbotQuery: true });
  }
}

async function ensureClauseCatalog(specNo) {
  if (state.clauseCatalogBySpec[specNo]) {
    return state.clauseCatalogBySpec[specNo];
  }

  const scope = getBoardScope();
  const releaseData = encodeURIComponent(scope.releaseData);
  const release = encodeURIComponent(scope.release);
  const response = await apiGet(
    `/api/clause-browser/documents/${encodeURIComponent(specNo)}/clauses?includeAll=true&limit=5000&releaseData=${releaseData}&release=${release}`
  );
  const items = response.data.items;
  const byId = {};
  const childrenByParent = {};
  const rootIds = [];

  items.forEach((item) => {
    byId[item.clauseId] = item;
  });

  items.forEach((item) => {
    const parentId = item.parentClauseId || "";
    const existing = childrenByParent[parentId] || [];
    childrenByParent[parentId] = [...existing, item.clauseId];
  });

  items.forEach((item) => {
    if (!item.parentClauseId || !byId[item.parentClauseId]) {
      rootIds.push(item.clauseId);
    }
  });

  const catalog = { items, byId, childrenByParent, rootIds };
  state.clauseCatalogBySpec = { ...state.clauseCatalogBySpec, [specNo]: catalog };
  return catalog;
}

function renderClauseTree() {
  if (!state.activeSpecNo) {
    elements.clauseTreeList.innerHTML =
      state.ui.clauseQuery
        ? '<div class="muted">현재 검색어와 일치하는 문서를 왼쪽에서 선택하세요. 절 번호, 절 제목, 본문으로 문서를 먼저 추릴 수 있습니다.</div>'
        : '<div class="muted">먼저 왼쪽에서 문서를 선택하세요. 절 검색은 문서 선택 전에도 절 번호, 절 제목, 본문 기준으로 문서를 좁히는 데 사용할 수 있습니다.</div>';
    return;
  }

  const catalog = state.clauseCatalogBySpec[state.activeSpecNo];
  if (!catalog) {
    elements.clauseTreeList.innerHTML = '<div class="muted">절 트리를 불러오는 중입니다.</div>';
    return;
  }

  const query = state.ui.clauseQuery.toLowerCase();
  const visibleRootIds = query
    ? catalog.rootIds.filter((clauseId) => branchMatchesQuery(clauseId, catalog, query))
    : catalog.rootIds;

  if (!visibleRootIds.length) {
    elements.clauseTreeList.innerHTML = '<div class="muted">일치하는 절이 없습니다.</div>';
    return;
  }

  elements.clauseTreeList.innerHTML = `
    <div class="clause-branch">
      ${visibleRootIds.map((clauseId) => renderClauseBranch(clauseId, catalog, query)).join("")}
    </div>
  `;

  elements.clauseTreeList.querySelectorAll("[data-action='load-clause']").forEach((button) => {
    button.addEventListener("click", async () => {
      await loadClause(button.dataset.clauseId);
    });
  });

  updateClauseTreeSummary(visibleRootIds.length);
}

function renderClauseBranch(clauseId, catalog, query) {
  const item = catalog.byId[clauseId];
  const childIds = (catalog.childrenByParent[clauseId] || []).filter((childId) => !query || branchMatchesQuery(childId, catalog, query));
  const loaded = Boolean(findNodeByKey(`${state.activeSpecNo}:${clauseId}`));

  return `
    <div class="clause-branch">
      <div class="clause-line">
        <span class="clause-bullet">-</span>
        <button class="clause-link" data-action="load-clause" data-clause-id="${escapeHtml(item.clauseId)}">
          ${escapeHtml(item.clauseId)} ${escapeHtml(item.clauseTitle)}
        </button>
        <span class="muted">${loaded ? "loaded" : ""}</span>
      </div>
      ${childIds.length ? `<div class="clause-children">${childIds.map((childId) => renderClauseBranch(childId, catalog, query)).join("")}</div>` : ""}
    </div>
  `;
}

function branchMatchesQuery(clauseId, catalog, query) {
  const item = catalog.byId[clauseId];
  if (!item) {
    return false;
  }
  const haystack = [item.searchText || "", item.clauseId, item.clauseTitle, item.textPreview || "", (item.clausePath || []).join(" ")]
    .join(" ")
    .toLowerCase();
  if (haystack.includes(query)) {
    return true;
  }
  return (catalog.childrenByParent[clauseId] || []).some((childId) => branchMatchesQuery(childId, catalog, query));
}

function updateClauseTreeSummary(visibleRootCount = null) {
  if (!state.activeSpecNo) {
    elements.pickerSelectionSummary.textContent = state.ui.clauseQuery
      ? `절/본문 검색어 "${state.ui.clauseQuery}" 로 문서를 먼저 추리는 중입니다.`
      : "문서를 먼저 선택하세요. 절 검색으로 문서를 먼저 좁힐 수도 있습니다.";
    return;
  }
  elements.pickerSelectionSummary.textContent =
    visibleRootCount === null
      ? `${state.activeSpecNo} 문서 선택됨. "문서 검색" 버튼을 다시 눌러 다른 문서를 고를 수 있습니다.`
      : `${state.activeSpecNo} 문서 선택됨. 현재 표시된 최상위 절 ${visibleRootCount}개. 제목 클릭 시 하위 절까지 함께 추가됩니다.`;
}

async function loadClause(clauseId) {
  return loadClauseWithSpec(state.activeSpecNo, clauseId);
}

async function loadClauseWithSpec(specNo, clauseId) {
  if (!specNo) {
    setMessage("먼저 문서를 선택하세요.", true);
    return null;
  }
  if (!beginBusy("절을 불러오는 중입니다.", { allowDuringSpecbotQuery: true })) {
    return null;
  }
  const key = `${specNo}:${clauseId}`;
  const existing = findNodeByKey(key);
  if (existing) {
    endBusy({ allowDuringSpecbotQuery: true });
    closePicker();
    focusNode(key);
    setMessage(`이미 로드된 절입니다. ${clauseId} 위치로 이동했습니다.`, false);
    return existing;
  }

  const loadedAncestor = findLoadedAncestor(specNo, clauseId);
  if (loadedAncestor) {
    endBusy({ allowDuringSpecbotQuery: true });
    closePicker();
    focusNode(loadedAncestor.key);
    setMessage(`이미 로드된 상위 절에 포함되어 있습니다. ${loadedAncestor.clauseId} 위치로 이동했습니다.`, false);
    return loadedAncestor;
  }

  try {
    const scope = getBoardScope();
    const releaseData = encodeURIComponent(scope.releaseData);
    const release = encodeURIComponent(scope.release);
    const response = await apiGet(
      `/api/clause-browser/documents/${encodeURIComponent(specNo)}/clauses/${encodeURIComponent(clauseId)}/subtree?releaseData=${releaseData}&release=${release}`
    );
    const subtree = ensureNodeStableBlockIds(response.data);
    expandAll(subtree);
    state.loadedRoots = mergeLoadedRoot(state.loadedRoots, subtree);
    syncClauseAnnotationBlockReferences(subtree.key);
    pruneSpecbotResultsByCurrentExclusions();
    state.ui.focusedKey = subtree.key;
    persistSessionState();
    closePicker();
    renderLoadedTree();
    renderSelectedClauseList();
    renderClauseTree();
    setMessage(`${clauseId} 절과 하위 절을 불러왔습니다.`, false);
    return subtree;
  } catch (error) {
    if (!isAbortedRequestError(error)) {
      setMessage(error.message, true);
    }
    return null;
  } finally {
    endBusy({ allowDuringSpecbotQuery: true });
  }
}

async function loadClauseFromSpec(specNo, clauseId) {
  if (state.activeSpecNo !== specNo) {
    await selectDocument(specNo);
  }
  await loadClauseWithSpec(specNo, clauseId);
}

function expandAll(node) {
  state.ui.expandedKeys = new Set([...state.ui.expandedKeys, node.key]);
  (node.children || []).forEach(expandAll);
}

function renderLoadedTree() {
  void destroyClauseEditorsIn(elements.treeContainer);
  const sortedRoots = [...state.loadedRoots].sort(compareLoadedNodes);
  const count = countNodes(sortedRoots);
  elements.loadedSummary.textContent = `${count} clauses loaded`;
  renderTranslationStatus();
  if (!sortedRoots.length) {
    elements.treeContainer.innerHTML = '<div class="muted">왼쪽의 문서 검색 버튼으로 문서를 고른 뒤, 절 제목을 클릭해 추가하세요.</div>';
    state.ui.viewportKey = "";
    persistSessionState();
    return;
  }
  const grouped = groupRootsBySpec(sortedRoots);
  elements.treeContainer.innerHTML = Object.entries(grouped)
    .map(([specNo, nodes]) => renderLoadedSpecGroup(specNo, nodes))
    .join("");
  bindTreeEvents();
  renderClauseNoteModal();
  syncViewportSelection();
}

function rerenderLoadedNode(nodeKey, { refreshSelectedList = false, refreshClauseTree = false, refreshClauseNoteModal = true } = {}) {
  const node = findNodeByKey(nodeKey);
  const current = document.getElementById(`node-${escapeKey(nodeKey)}`);
  if (!node || !current) {
    renderLoadedTree();
    if (refreshSelectedList) {
      renderSelectedClauseList();
    }
    if (refreshClauseTree) {
      renderClauseTree();
    }
    if (refreshClauseNoteModal) {
      renderClauseNoteModal();
    }
    return;
  }
  void destroyClauseEditorsIn(current);
  current.outerHTML = renderNode(node);
  const next = document.getElementById(`node-${escapeKey(nodeKey)}`);
  if (next) {
    bindTreeEvents(next);
  }
  if (refreshSelectedList) {
    renderSelectedClauseList();
  }
  if (refreshClauseTree) {
    renderClauseTree();
  }
  if (refreshClauseNoteModal && state.ui.clauseNoteModalKey === nodeKey) {
    renderClauseNoteModal();
  }
  syncViewportSelection();
}

function rerenderLoadedNodes(nodeKeys, options = {}) {
  const uniqueKeys = [...new Set((nodeKeys || []).filter(Boolean))];
  if (!uniqueKeys.length) {
    return;
  }
  uniqueKeys.forEach((nodeKey) => {
    rerenderLoadedNode(nodeKey, {
      ...options,
      refreshSelectedList: false,
      refreshClauseTree: false,
      refreshClauseNoteModal: false,
    });
  });
  if (options.refreshSelectedList) {
    renderSelectedClauseList();
  }
  if (options.refreshClauseTree) {
    renderClauseTree();
  }
  if (options.refreshClauseNoteModal) {
    renderClauseNoteModal();
  }
}

function renderLoadedSpecGroup(specNo, nodes) {
  const collapsed = state.ui.collapsedLoadedSpecs.has(specNo);
  const clauseCount = countNodes(nodes);
  return `
    <section class="tree-spec-group">
      <article class="tree-node tree-spec-root">
        <div class="tree-header tree-spec-header">
          <div class="tree-title">
            <button data-action="toggle-loaded-spec" data-spec-no="${escapeHtml(specNo)}">${collapsed ? "+" : "−"}</button>
            <div class="tree-title-text">
              <h3>${escapeHtml(specNo)}</h3>
              <div class="tree-meta">${clauseCount} clauses loaded</div>
            </div>
          </div>
        </div>
        ${collapsed ? "" : `<div class="tree-body tree-spec-body"><div class="tree-spec-children">${nodes.map((node) => renderNode(node)).join("")}</div></div>`}
      </article>
    </section>
  `;
}

function renderNode(node) {
  const expanded = state.ui.expandedKeys.has(node.key);
  const focusedClass = state.ui.focusedKey === node.key ? "focused" : "";
  const clauseNoteToggleHtml = renderClauseNoteToggle(node.key);
  const hasBlocks = Boolean((node.blocks || []).length);
  const hasChildren = Boolean((node.children || []).length);
  const childrenHtml =
    expanded && hasChildren
      ? `<div class="tree-children">${node.children.map((child) => renderNode(child)).join("")}</div>`
      : "";
  const bodyHtml = expanded
    ? `
      <div class="tree-body ${hasBlocks ? "" : "tree-body-compact"}">
        ${hasBlocks ? (isBoardEditMode() ? renderEditorSection(node) : renderBlocks(node)) : ""}
        ${childrenHtml}
      </div>
    `
    : "";

  return `
    <article class="tree-node ${focusedClass}" id="node-${escapeKey(node.key)}" data-node-key="${escapeHtml(node.key)}">
      <div class="tree-header">
        <div class="tree-title">
          <button data-action="toggle-node" data-node-key="${escapeHtml(node.key)}">${expanded ? "−" : "+"}</button>
          <div class="tree-title-text">
            <h3>${escapeHtml(node.clauseId)} ${escapeHtml(node.clauseTitle)}</h3>
            <div class="tree-meta">${escapeHtml(node.specNo)} · ${node.descendantCount} descendants</div>
          </div>
        </div>
        <div class="tree-actions">
          <button class="icon-button ghost" title="번역 후 메모" aria-label="번역 후 메모" data-action="translate-clause" data-node-key="${escapeHtml(node.key)}">T</button>
          ${clauseNoteToggleHtml}
          ${isBoardViewMode() ? "" : `<button class="icon-button danger" title="이 절 제거" aria-label="이 절 제거" data-action="remove-node" data-node-key="${escapeHtml(node.key)}">✕</button>`}
        </div>
      </div>
      ${bodyHtml}
    </article>
  `;
}

function renderEditorSection(node) {
  return `${renderEditorHost(node)}${renderEditorSelectionNotes(node)}`;
}

function renderEditorHost(node) {
  return `
    <div
      class="clause-editor-host"
      data-editor-node-key="${escapeHtml(node.key)}"
      data-editor-clause-id="${escapeHtml(node.clauseId || "")}"
    >${buildEditorHtmlFromBlocks(node.key, node.blocks || [])}</div>
  `;
}

function renderEditorSelectionNotes(node) {
  const notes = (state.ui.notes || [])
    .filter((note) => note.type === "selection" && note.clauseKey === node.key)
    .sort((left, right) =>
      getResolvedBlockIndexForReference(left.clauseKey, left.blockIndex, left.blockId) - getResolvedBlockIndexForReference(right.clauseKey, right.blockIndex, right.blockId) ||
      Number(left.rowIndex ?? -1) - Number(right.rowIndex ?? -1) ||
      Number(left.cellIndex ?? -1) - Number(right.cellIndex ?? -1)
    );
  if (!notes.length) {
    return "";
  }
  return `
    <div class="editor-selection-note-list" data-editor-note-list="${escapeHtml(node.key)}">
      ${notes
        .map((note) => {
          const resolvedBlockIndex = getResolvedBlockIndexForReference(note.clauseKey, note.blockIndex, note.blockId);
          const blockLabel = resolvedBlockIndex >= 0 ? `block ${resolvedBlockIndex + 1}` : "block ?";
          const location =
            Number(note.rowIndex ?? -1) >= 0
              ? `row ${Number(note.rowIndex ?? -1) + 1}${Number(note.cellIndex ?? -1) >= 0 ? ` · cell ${Number(note.cellIndex ?? -1) + 1}` : ""}`
              : "paragraph";
          return `
            <article class="clause-note-card editor-note-card ${note.collapsed ? "collapsed" : ""}" data-note-id="${escapeHtml(note.id)}">
              <div class="clause-note-meta">
                <div class="clause-note-meta-main">
                  <strong class="note-kind">선택 메모</strong>
                  <span class="muted">${escapeHtml(blockLabel)} · ${escapeHtml(location)}</span>
                </div>
                <div class="clause-note-meta-actions">
                  <button class="icon-button ghost note-delete-button" title="삭제" aria-label="삭제" data-action="delete-note" data-note-id="${escapeHtml(note.id)}">✕</button>
                </div>
              </div>
              <div class="clause-note-body">
                <label class="field">
                  <textarea class="clause-note-textarea" data-action="edit-note-translation" data-note-id="${escapeHtml(note.id)}" rows="4" placeholder="메모를 입력하세요.">${escapeHtml(
                    note.translation || ""
                  )}</textarea>
                </label>
              </div>
            </article>
          `;
        })
        .join("")}
    </div>
  `;
}

function renderTranslationStatus() {
  const job = state.ui.translationJob;
  const task = state.ui.translationTask;
  if ((!job || !job.totalRequests) && !task) {
    elements.translationStatus.classList.add("hidden");
    elements.translationStatus.innerHTML = "";
    return;
  }
  if (!job || !job.totalRequests) {
    const active = task?.status === "queued" || task?.status === "started";
    const label = task?.label ? escapeHtml(task.label) : "번역";
    const detail =
      task?.status === "queued"
        ? `대기 중${Number(task.queuedPosition || 0) > 0 ? ` · 대기열 ${Number(task.queuedPosition)}번째` : ""}`
        : task?.status === "started"
          ? "실행 중"
          : "완료";
    elements.translationStatus.classList.remove("hidden");
    elements.translationStatus.innerHTML = `
      <div class="translation-status-card ${active ? "active" : ""}">
        <div class="translation-status-main">
          ${active ? '<span class="spinner" aria-hidden="true"></span>' : ""}
          <strong>${label}</strong>
          <span class="muted">${detail}</span>
        </div>
      </div>
    `;
    return;
  }
  const done = Number(job.completedRequests || 0);
  const total = Number(job.totalRequests || 0);
  const active = done < total;
  const currentLabel = job.currentLabel ? escapeHtml(job.currentLabel) : "";
  elements.translationStatus.classList.remove("hidden");
  elements.translationStatus.innerHTML = `
    <div class="translation-status-card ${active ? "active" : ""}">
      <div class="translation-status-main">
        ${active ? '<span class="spinner" aria-hidden="true"></span>' : ""}
        <strong>${active ? "절 번역 진행 중" : "절 번역 완료"}</strong>
        <span class="muted">${done} / ${total}</span>
      </div>
      <div class="translation-status-detail">
        요청 기준 진행 상황
        ${currentLabel ? " · " : ""}
        ${currentLabel}
      </div>
    </div>
  `;
}

function renderBlocks(node) {
  const blocks = node.blocks || [];
  if (!blocks.length) {
    return "";
  }
  return blocks
    .map((block, index) => {
      if (block.type === "paragraph") {
        return renderParagraphBlock(node, block, index);
      }
      if (block.type === "table") {
        return renderTableBlock(node, block, index);
      }
      if (block.type === "image") {
        const src = block.src || "";
        const extension = src.split(".").pop()?.toLowerCase() || "";
        if (extension === "wmf" || extension === "emf") {
          const svgSrc = src.replace(/\.wmf$/i, ".svg").replace(/\.emf$/i, ".svg");
          return `
            <figure class="docx-figure" tabindex="0" data-block-type="image" data-clause-key="${escapeHtml(node.key)}" data-block-index="${index}">
              <img src="${escapeHtml(svgSrc)}" alt="${escapeHtml(block.alt || "")}" />
              <figcaption class="muted">${escapeHtml(block.alt || "Image")}</figcaption>
            </figure>
          `;
        }
        return `
          <figure class="docx-figure" tabindex="0" data-block-type="image" data-clause-key="${escapeHtml(node.key)}" data-block-index="${index}">
            <img src="${escapeHtml(src)}" alt="${escapeHtml(block.alt || "")}" />
            <figcaption class="muted">${escapeHtml(block.alt || "Image")}</figcaption>
          </figure>
        `;
      }
      return "";
    })
    .join("");
}

function buildEditorHtmlFromBlocks(clauseKey, blocks) {
  return (blocks || [])
    .map((block, blockIndex) => {
      const blockId = String(block.id || "");
      if (block.type === "paragraph") {
        const text = String(block.text || "");
        const blockHighlighted = hasBlockHighlight(clauseKey, blockIndex);
        const className = blockHighlighted ? ' class="editor-block is-highlighted"' : ' class="editor-block"';
        return `<p${className} data-editor-block-index="${blockIndex}" data-editor-block-id="${escapeHtml(blockId)}">${escapeHtml(text || "") || "<br />"}</p>`;
      }
      if (block.type === "image") {
        const src = String(block.src || "").trim();
        const alt = String(block.alt || "").trim();
        const blockHighlighted = hasBlockHighlight(clauseKey, blockIndex);
        const className = blockHighlighted ? ' class="editor-block is-highlighted"' : ' class="editor-block"';
        return src ? `<p${className} data-editor-block-index="${blockIndex}" data-editor-block-id="${escapeHtml(blockId)}"><img src="${escapeHtml(src)}" alt="${escapeHtml(alt)}" /></p>` : "";
      }
      if (block.type === "table") {
        return buildEditorHtmlForTable(clauseKey, blockIndex, block);
      }
      return "";
    })
    .join("");
}

function buildEditorHtmlForTable(clauseKey, blockIndex, block) {
  const cells = Array.isArray(block.cells) ? block.cells : [];
  const rows = Array.isArray(block.rows) ? block.rows : [];
  const highlightedRows = getHighlightedRowIndexes(clauseKey, blockIndex, block);
  const tableRows = cells.length
    ? cells
        .map(
          (row, rowIndex) => `<tr class="${highlightedRows.has(rowIndex) ? "is-highlighted" : ""}">${row
            .map((cell, cellIndex) => {
              const tag = cell.header ? "th" : "td";
              const rowspan = Number(cell.rowspan || 1) > 1 ? ` rowspan="${Number(cell.rowspan || 1)}"` : "";
              const colspan = Number(cell.colspan || 1) > 1 ? ` colspan="${Number(cell.colspan || 1)}"` : "";
              const highlightedCells = getHighlightedCellIndexes(clauseKey, blockIndex, rowIndex);
              const className = highlightedRows.has(rowIndex) || highlightedCells.has(cellIndex) ? ' class="is-highlighted"' : "";
              return `<${tag}${className} data-editor-cell-id="${escapeHtml(String(cell.id || ""))}"${rowspan}${colspan}>${escapeHtml(cell.text || "") || "<br />"}</${tag}>`;
            })
            .join("")}</tr>`
        )
        .join("")
    : rows
        .map(
          (row, rowIndex) => `<tr class="${highlightedRows.has(rowIndex) ? "is-highlighted" : ""}">${row
            .map((cell, cellIndex) => {
              const tag = rowIndex === 0 ? "th" : "td";
              const highlightedCells = getHighlightedCellIndexes(clauseKey, blockIndex, rowIndex);
              const className = highlightedRows.has(rowIndex) || highlightedCells.has(cellIndex) ? ' class="is-highlighted"' : "";
              return `<${tag}${className}>${escapeHtml(String(cell || "")) || "<br />"}</${tag}>`;
            })
            .join("")}</tr>`
        )
        .join("");
  const blockHighlighted = hasBlockHighlight(clauseKey, blockIndex);
  const tableClass = blockHighlighted ? ' class="editor-block is-highlighted"' : ' class="editor-block"';
  return `<table${tableClass} data-editor-block-index="${blockIndex}" data-editor-block-id="${escapeHtml(String(block.id || ""))}"><tbody>${tableRows}</tbody></table>`;
}

function parseEditorHtmlToBlocks(html) {
  const parser = new DOMParser();
  const doc = parser.parseFromString(`<body>${html || ""}</body>`, "text/html");
  const blocks = [];
  [...doc.body.childNodes].forEach((node) => {
    if (node.nodeType === Node.TEXT_NODE) {
      const text = String(node.textContent || "").trim();
      if (text) {
        blocks.push({ type: "paragraph", text });
      }
      return;
    }
    if (!(node instanceof HTMLElement)) {
      return;
    }
    const tag = node.tagName.toLowerCase();
    if (tag === "table") {
      const tableBlock = parseEditorTableToBlock(node);
      if (tableBlock) {
        blocks.push(tableBlock);
      }
      return;
    }
    if (node.classList.contains("editor-inline-note")) {
      return;
    }
    if (tag === "img") {
      const src = String(node.getAttribute("src") || "").trim();
      if (src) {
        blocks.push({ id: createStableBlockId(), type: "image", src, alt: String(node.getAttribute("alt") || "").trim() });
      }
      return;
    }
    if (tag === "p" || tag === "div" || /^h[1-6]$/.test(tag)) {
      const onlyImage = node.children.length === 1 && node.firstElementChild?.tagName.toLowerCase() === "img";
      if (onlyImage) {
        const image = node.firstElementChild;
        const src = String(image?.getAttribute("src") || "").trim();
        if (src) {
          blocks.push({ id: String(node.getAttribute("data-editor-block-id") || "") || createStableBlockId(), type: "image", src, alt: String(image?.getAttribute("alt") || "").trim() });
        }
        return;
      }
      const text = normalizeEditorText(node.innerText || node.textContent || "");
      if (text) {
        blocks.push({ id: String(node.getAttribute("data-editor-block-id") || "") || createStableBlockId(), type: "paragraph", text });
      }
      return;
    }
    const text = normalizeEditorText(node.innerText || node.textContent || "");
    if (text) {
      blocks.push({ id: String(node.getAttribute("data-editor-block-id") || "") || createStableBlockId(), type: "paragraph", text });
    }
  });
  return ensureBlocksHaveStableIds(blocks);
}

function parseEditorTableToBlock(table) {
  const rows = [...table.querySelectorAll("tr")];
  if (!rows.length) {
    return null;
  }
  const cells = rows.map((row) =>
    [...row.children]
      .filter((cell) => /^(td|th)$/i.test(cell.tagName))
      .map((cell) => ({
        id: String(cell.getAttribute("data-editor-cell-id") || "").trim() || createStableCellId(),
        text: normalizeEditorText(cell.innerText || cell.textContent || ""),
        header: cell.tagName.toLowerCase() === "th",
        rowspan: Math.max(1, Number(cell.getAttribute("rowspan") || 1)),
        colspan: Math.max(1, Number(cell.getAttribute("colspan") || 1)),
      }))
  );
  return { id: String(table.getAttribute("data-editor-block-id") || "") || createStableBlockId(), type: "table", cells };
}

function getBlockByIndex(clauseKey, blockIndex) {
  const node = findNodeByKey(clauseKey);
  return node?.blocks?.[blockIndex] || null;
}

function getBlockIdByIndex(clauseKey, blockIndex) {
  const block = getBlockByIndex(clauseKey, blockIndex);
  return String(block?.id || "");
}

function getBlockIndexById(clauseKey, blockId) {
  const normalizedBlockId = String(blockId || "").trim();
  if (!normalizedBlockId) {
    return -1;
  }
  const node = findNodeByKey(clauseKey);
  if (!node?.blocks?.length) {
    return -1;
  }
  return node.blocks.findIndex((block) => String(block?.id || "").trim() === normalizedBlockId);
}

function getTableCellPositionById(clauseKey, blockIndex, cellId, blockId = getBlockIdByIndex(clauseKey, blockIndex)) {
  const resolvedBlockIndex = getResolvedBlockIndexForReference(clauseKey, blockIndex, blockId);
  const block = getBlockByIndex(clauseKey, resolvedBlockIndex);
  const normalizedCellId = String(cellId || "").trim();
  if (!block || block.type !== "table" || !normalizedCellId || !Array.isArray(block.cells)) {
    return null;
  }
  for (let rowIndex = 0; rowIndex < block.cells.length; rowIndex += 1) {
    const row = block.cells[rowIndex] || [];
    for (let cellIndex = 0; cellIndex < row.length; cellIndex += 1) {
      const cell = row[cellIndex];
      if (String(cell?.id || "").trim() === normalizedCellId) {
        const rowText = normalizeRowText(row.map((item) => normalizeTableDisplayText(item?.text || "")));
        return { rowIndex, cellIndex, rowText };
      }
    }
  }
  return null;
}

function getResolvedBlockIndexForReference(clauseKey, blockIndex, blockId = "") {
  const resolvedFromId = getBlockIndexById(clauseKey, blockId);
  return resolvedFromId >= 0 ? resolvedFromId : Number(blockIndex ?? -1);
}

function syncBlockReferenceForItem(item) {
  const normalizedClauseKey = String(item?.clauseKey || "").trim();
  if (!normalizedClauseKey) {
    return item;
  }
  const normalizedBlockId = String(item?.blockId || "").trim();
  if (normalizedBlockId) {
    const nextBlockIndex = getBlockIndexById(normalizedClauseKey, normalizedBlockId);
    if (nextBlockIndex < 0) {
      return null;
    }
    const nextItem = { ...item, blockIndex: nextBlockIndex };
    const normalizedCellId = String(item?.cellId || "").trim();
    if (normalizedCellId) {
      const position = getTableCellPositionById(normalizedClauseKey, nextBlockIndex, normalizedCellId, normalizedBlockId);
      if (!position) {
        return null;
      }
      return {
        ...nextItem,
        rowIndex: position.rowIndex,
        cellIndex: position.cellIndex,
        rowText: position.rowText,
      };
    }
    return nextItem;
  }
  const fallbackBlockIndex = Number(item?.blockIndex ?? -1);
  const fallbackBlockId = getBlockIdByIndex(normalizedClauseKey, fallbackBlockIndex);
  if (!fallbackBlockId) {
    return null;
  }
  const nextItem = {
    ...item,
    blockId: fallbackBlockId,
    blockIndex: fallbackBlockIndex,
  };
  const normalizedCellId = String(item?.cellId || "").trim();
  if (normalizedCellId) {
    const position = getTableCellPositionById(normalizedClauseKey, fallbackBlockIndex, normalizedCellId, fallbackBlockId);
    if (!position) {
      return null;
    }
    return {
      ...nextItem,
      rowIndex: position.rowIndex,
      cellIndex: position.cellIndex,
      rowText: position.rowText,
    };
  }
  return nextItem;
}

function syncClauseAnnotationBlockReferences(clauseKey) {
  const normalizedClauseKey = String(clauseKey || "").trim();
  if (!normalizedClauseKey) {
    return;
  }
  state.ui.notes = (state.ui.notes || []).flatMap((note) => {
    if (note.type !== "selection" || note.clauseKey !== normalizedClauseKey) {
      return [note];
    }
    const synced = syncBlockReferenceForItem(note);
    return synced ? [synced] : [];
  });
  state.ui.highlights = (state.ui.highlights || []).flatMap((item) => {
    if (item.clauseKey !== normalizedClauseKey) {
      return [item];
    }
    const synced = syncBlockReferenceForItem(item);
    return synced ? [synced] : [];
  });
}

function syncAllAnnotationBlockReferences() {
  const clauseKeys = new Set([
    ...(state.ui.notes || []).map((note) => note?.clauseKey || ""),
    ...(state.ui.highlights || []).map((item) => item?.clauseKey || ""),
  ]);
  clauseKeys.forEach((clauseKey) => {
    if (clauseKey) {
      syncClauseAnnotationBlockReferences(clauseKey);
    }
  });
}

function blockReferenceMatches(item, clauseKey, blockIndex, blockId = "") {
  if (item.clauseKey !== clauseKey) {
    return false;
  }
  const currentBlockId = String(item.blockId || "").trim();
  if (blockId && currentBlockId) {
    return currentBlockId === blockId;
  }
  return Number(item.blockIndex) === Number(blockIndex);
}

function renderTableBlock(node, block, index) {
  const cellRows = block.cells || [];
  const rows = block.rows || [];
  const highlightedRowIndexes = getHighlightedRowIndexes(node.key, index, block, String(block.id || ""));
  const totalColumnCount = cellRows.length
    ? Math.max(...cellRows.map((row) => row.reduce((total, cell) => total + Number(cell.colspan || 1), 0)))
    : Math.max(...rows.map((row) => row.length));
  const tableBody =
    cellRows.length
      ? cellRows
          .map((row, rowIndex) => {
            const rowText = normalizeRowText(row.map((cell) => normalizeTableDisplayText(cell.text || "")));
            const highlighted = highlightedRowIndexes.has(rowIndex);
            const highlightedCellIndexes = getHighlightedCellIndexes(node.key, index, rowIndex);
            let visualColumnIndex = 0;
            return `
              <tr class="${highlighted ? "is-highlighted" : ""}">
                ${row
                  .map((cell, cellIndex) => {
                    const tag = cell.header ? "th" : "td";
                    const rowspan = Number(cell.rowspan || 1) > 1 ? ` rowspan="${Number(cell.rowspan || 1)}"` : "";
                    const colspan = Number(cell.colspan || 1) > 1 ? ` colspan="${Number(cell.colspan || 1)}"` : "";
                    const hasExpandedSelectionNotes = getSelectionNotesForTarget(node.key, index, rowIndex, cellIndex, String(block.id || ""), String(cell.id || "")).some((note) => !note.collapsed);
                    const rowToggleHtml = renderSelectionNoteToggle(node.key, index, rowIndex, cellIndex, true, String(block.id || ""), String(cell.id || ""));
                    const cellHighlighted = highlighted || highlightedCellIndexes.has(cellIndex) || hasExpandedSelectionNotes;
                    const cellClass = cellHighlighted ? "tree-text table-cell-content is-highlighted" : "tree-text table-cell-content";
                    const currentColumnIndex = visualColumnIndex;
                    visualColumnIndex += Number(cell.colspan || 1);
                    return `<${tag} class="${cellClass}" data-clause-key="${escapeHtml(node.key)}" data-block-id="${escapeHtml(String(block.id || ""))}" data-cell-id="${escapeHtml(String(cell.id || ""))}" data-block-index="${index}" data-row-index="${rowIndex}" data-cell-index="${cellIndex}" data-col-index="${currentColumnIndex}" data-row-text="${escapeHtml(rowText)}"${rowspan}${colspan}>
                      <div class="table-cell-inner">
                        <span class="table-cell-text">${escapeHtml(normalizeTableDisplayText(cell.text || ""))}</span>
                        ${rowToggleHtml}
                      </div>
                    </${tag}>`;
                  })
                  .join("")}
              </tr>
              ${renderTableRowNoteRow(node.key, index, rowIndex, totalColumnCount)}
            `;
          })
          .join("")
      : rows
          .map((row, rowIndex) => {
            const normalizedRow = row.map((cell) => normalizeTableDisplayText(cell));
            const rowText = normalizeRowText(normalizedRow);
            const highlighted = highlightedRowIndexes.has(rowIndex);
            const highlightedCellIndexes = getHighlightedCellIndexes(node.key, index, rowIndex);
            return `
              <tr class="${highlighted ? "is-highlighted" : ""}">
                ${row
                  .map((cell, cellIndex) => {
                    const tag = rowIndex === 0 ? "th" : "td";
                    const hasExpandedSelectionNotes = getSelectionNotesForTarget(node.key, index, rowIndex, cellIndex, String(block.id || ""), "").some((note) => !note.collapsed);
                    const rowToggleHtml = renderSelectionNoteToggle(node.key, index, rowIndex, cellIndex, true, String(block.id || ""), "");
                    const cellHighlighted = highlighted || highlightedCellIndexes.has(cellIndex) || hasExpandedSelectionNotes;
                    const cellClass = cellHighlighted ? "tree-text table-cell-content is-highlighted" : "tree-text table-cell-content";
                    return `<${tag} class="${cellClass}" data-clause-key="${escapeHtml(node.key)}" data-block-id="${escapeHtml(String(block.id || ""))}" data-cell-id="" data-block-index="${index}" data-row-index="${rowIndex}" data-cell-index="${cellIndex}" data-col-index="${cellIndex}" data-row-text="${escapeHtml(rowText)}">
                      <div class="table-cell-inner">
                        <span class="table-cell-text">${escapeHtml(normalizeTableDisplayText(cell || ""))}</span>
                        ${rowToggleHtml}
                      </div>
                    </${tag}>`;
                  })
                  .join("")}
              </tr>
              ${renderTableRowNoteRow(node.key, index, rowIndex, totalColumnCount)}
            `;
          })
          .join("");

  return `
    <div class="table-block ${hasBlockHighlight(node.key, index) ? "is-highlighted" : ""}">
      <div class="docx-table-wrap" data-clause-key="${escapeHtml(node.key)}" data-block-id="${escapeHtml(String(block.id || ""))}" data-block-index="${index}">
        <table class="docx-table">
          <tbody>
            ${tableBody}
          </tbody>
        </table>
      </div>
    </div>
  `;
}

function renderTableRowNoteRow(clauseKey, blockIndex, rowIndex, colspan) {
  const notesHtml = renderSelectionNotes(clauseKey, blockIndex, rowIndex, null, getBlockIdByIndex(clauseKey, blockIndex));
  if (!notesHtml) {
    return "";
  }
  return `
    <tr class="table-note-detail-row">
      <td colspan="${colspan}">
        ${notesHtml}
      </td>
    </tr>
  `;
}

function renderParagraphBlock(node, block, index) {
  const paragraphClass = getParagraphClass(block.text || "", block);
  const paragraphStyle = getParagraphInlineStyle(block);
  const blockId = String(block.id || "");
  const selectionToggleHtml = renderSelectionNoteToggle(node.key, index, -1, -1, false, blockId);
  const selectionNotesHtml = renderSelectionNotes(node.key, index, -1, -1, blockId);
  const hasExpandedSelectionNotes = getSelectionNotesForTarget(node.key, index, -1, -1, blockId).some((note) => !note.collapsed);
  return `
    <div class="paragraph-block ${hasExpandedSelectionNotes ? "has-selection-note" : ""} ${hasBlockHighlight(node.key, index) ? "is-highlighted" : ""}">
      <div class="paragraph-note-row">
        <p class="${paragraphClass}" style="${escapeHtml(paragraphStyle)}" data-clause-key="${escapeHtml(node.key)}" data-block-id="${escapeHtml(blockId)}" data-block-index="${index}" data-row-index="-1" data-cell-index="-1" data-row-text="${escapeHtml(String(block.text || "").trim())}">${escapeHtml(block.text || "")}</p>
        ${selectionToggleHtml}
      </div>
      ${selectionNotesHtml}
    </div>
  `;
}

function getParagraphInlineStyle(block) {
  const format = block?.format || {};
  const text = String(block?.text || "").trim();
  const styles = [];
  const hasDocxLeftIndent =
    (Number.isFinite(Number(format.leftIndentPt)) && Number(format.leftIndentPt) !== 0) ||
    (Number.isFinite(Number(format.leftIndentPx)) && Number(format.leftIndentPx) !== 0);
  const hasDocxTextIndent =
    (Number.isFinite(Number(format.textIndentPt)) && Number(format.textIndentPt) !== 0) ||
    (Number.isFinite(Number(format.textIndentPx)) && Number(format.textIndentPx) !== 0);
  if (Number.isFinite(Number(format.leftIndentPt)) && Number(format.leftIndentPt) !== 0) {
    styles.push(`margin-left:${Number(format.leftIndentPt)}pt`);
  } else if (Number.isFinite(Number(format.leftIndentPx)) && Number(format.leftIndentPx) !== 0) {
    styles.push(`margin-left:${Number(format.leftIndentPx)}px`);
  }
  const shouldUseHangingIndent =
    /^NOTE\s*:/i.test(text) ||
    /^(EXAMPLE|Examples?)\s*:/i.test(text) ||
    /^(WARNING|CAUTION)\s*:/i.test(text) ||
    /^(?:[-*•]|[A-Za-z]\)|\d+[A-Za-z]+\)|\d+\)|\d+[A-Za-z]+\.\s+|\d+\.\s+)/.test(text);
  if (
    hasDocxTextIndent &&
    Number.isFinite(Number(format.textIndentPt)) &&
    Number(format.textIndentPt) !== 0
  ) {
    styles.push(`text-indent:${Number(format.textIndentPt)}pt`);
  } else if (
    hasDocxTextIndent &&
    Number.isFinite(Number(format.textIndentPx)) &&
    Number(format.textIndentPx) !== 0
  ) {
    styles.push(`text-indent:${Number(format.textIndentPx)}px`);
  } else if (
    shouldUseHangingIndent &&
    Number.isFinite(Number(format.textIndentPt)) &&
    Number(format.textIndentPt) !== 0
  ) {
    styles.push(`text-indent:${Number(format.textIndentPt)}pt`);
  }
  if (!hasDocxLeftIndent && !hasDocxTextIndent && !shouldUseHangingIndent) {
    styles.push("padding-left:0");
  }
  return styles.join("; ");
}

function renderClauseNotes(clauseKey) {
  const notes = getNotesForClause(clauseKey).filter((note) => note.type === "clause");
  if (!notes.length) {
    return "";
  }
  return `
    <div class="clause-note-list">
      ${notes
        .map(
          (note) => `
            <article class="clause-note-card ${note.collapsed ? "collapsed" : ""}" data-note-id="${escapeHtml(note.id)}">
              <div class="clause-note-meta">
                <div class="clause-note-meta-main">
                  <strong class="note-kind">${note.type === "clause" ? "절 메모" : "선택 메모"}</strong>
                </div>
                <div class="clause-note-meta-actions">
                  <button class="icon-button ghost note-delete-button" title="삭제" aria-label="삭제" data-action="delete-note" data-note-id="${escapeHtml(note.id)}">✕</button>
                </div>
              </div>
              <div class="clause-note-body">
                <label class="field">
                  <textarea class="clause-note-textarea" data-action="edit-note-translation" data-note-id="${escapeHtml(note.id)}" rows="5" placeholder="번역 결과를 수정하세요.">${escapeHtml(
                    note.translation || ""
                  )}</textarea>
                </label>
              </div>
            </article>
          `
        )
        .join("")}
    </div>
  `;
}

function renderClauseNoteToggle(clauseKey) {
  const notes = getNotesForClause(clauseKey).filter((note) => note.type === "clause");
  if (!notes.length) {
    return "";
  }
  const expanded = state.ui.clauseNoteModalKey === clauseKey;
  return `
    <button
      class="icon-button note-toggle-button"
      title="절 메모 ${expanded ? "닫기" : "열기"}"
      aria-label="절 메모 ${expanded ? "닫기" : "열기"}"
      data-action="toggle-clause-notes"
      data-clause-key="${escapeHtml(clauseKey)}"
    >
      📝
    </button>
  `;
}

function renderSelectionNoteToggle(clauseKey, blockIndex, rowIndex = -1, cellIndex = -1, compact = false, blockId = "", cellId = "") {
  const notes = getSelectionNotesForTarget(clauseKey, blockIndex, rowIndex, cellIndex, blockId, cellId);
  if (!notes.length) {
    return "";
  }
  const expanded = notes.some((note) => !note.collapsed);
  const label = compact ? "📝" : `📝 ${notes.length}`;
  return `
    <button
      class="selection-note-toggle ${compact ? "compact" : ""} ${expanded ? "expanded" : ""}"
      title="선택 메모 ${notes.length}개"
      aria-label="선택 메모 ${notes.length}개"
      data-action="toggle-selection-notes"
      data-clause-key="${escapeHtml(clauseKey)}"
      data-block-id="${escapeHtml(blockId)}"
      data-block-index="${blockIndex}"
      data-row-index="${rowIndex}"
      data-cell-index="${cellIndex}"
      data-cell-id="${escapeHtml(cellId)}"
    >
      ${label}
    </button>
  `;
}

function renderSelectionNotes(clauseKey, blockIndex, rowIndex = -1, cellIndex = null, blockId = "", cellId = "") {
  const notes = getSelectionNotesForTarget(clauseKey, blockIndex, rowIndex, cellIndex, blockId, cellId);
  if (!notes.length) {
    return "";
  }
  const visibleNotes = notes.filter((note) => !note.collapsed);
  if (!visibleNotes.length) {
    return "";
  }
  return `
    <div class="selection-note-list">
      ${visibleNotes
        .map(
          (note) => `
            <article class="clause-note-card ${note.collapsed ? "collapsed" : ""}" data-note-id="${escapeHtml(note.id)}">
              <div class="clause-note-meta">
                <div class="clause-note-meta-main">
                  <strong class="note-kind">선택 메모</strong>
                </div>
                <div class="clause-note-meta-actions">
                  <button class="icon-button ghost note-delete-button" title="삭제" aria-label="삭제" data-action="delete-note" data-note-id="${escapeHtml(note.id)}">✕</button>
                </div>
              </div>
              <div class="clause-note-body ${note.collapsed ? "hidden" : ""}">
                <label class="field">
                  <textarea class="clause-note-textarea" data-action="edit-note-translation" data-note-id="${escapeHtml(note.id)}" rows="4" placeholder="번역 결과를 수정하세요.">${escapeHtml(
                    note.translation || ""
                  )}</textarea>
                </label>
              </div>
            </article>
          `
        )
        .join("")}
    </div>
  `;
}

function normalizeRowText(parts) {
  return String((parts || []).map((item) => String(item || "").trim()).filter(Boolean).join(" | "))
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase();
}

function normalizeTableDisplayText(value) {
  return String(value || "")
    .replace(/\s+/g, " ")
    .trim();
}

function normalizeHighlightText(value) {
  return String(value || "").replace(/\s+/g, " ").trim().toLowerCase();
}

function buildRowVariants(parts) {
  const normalizedParts = (parts || []).map((item) => normalizeTableDisplayText(item)).filter(Boolean);
  const variants = new Set();
  if (!normalizedParts.length) {
    return variants;
  }
  variants.add(normalizeHighlightText(normalizedParts.join(" | ")));
  variants.add(normalizeHighlightText(normalizedParts.join("; ")));
  if (normalizedParts.length > 1) {
    variants.add(normalizeHighlightText(normalizedParts.slice(1).join(" | ")));
    variants.add(normalizeHighlightText(normalizedParts.slice(1).join("; ")));
  }
  return variants;
}

function buildHighlightRowVariants(value) {
  const normalized = normalizeHighlightText(value);
  const variants = new Set();
  if (!normalized) {
    return variants;
  }
  variants.add(normalized);
  const pipeParts = normalized.split("|").map((item) => item.trim()).filter(Boolean);
  if (pipeParts.length) {
    variants.add(normalizeHighlightText(pipeParts.join(" | ")));
    variants.add(normalizeHighlightText(pipeParts.join("; ")));
    if (pipeParts.length > 1) {
      variants.add(normalizeHighlightText(pipeParts.slice(1).join(" | ")));
      variants.add(normalizeHighlightText(pipeParts.slice(1).join("; ")));
    }
  }
  const semicolonParts = normalized.split(";").map((item) => item.trim()).filter(Boolean);
  if (semicolonParts.length) {
    variants.add(normalizeHighlightText(semicolonParts.join(" | ")));
    variants.add(normalizeHighlightText(semicolonParts.join("; ")));
    if (semicolonParts.length > 1) {
      variants.add(normalizeHighlightText(semicolonParts.slice(1).join(" | ")));
      variants.add(normalizeHighlightText(semicolonParts.slice(1).join("; ")));
    }
  }
  return variants;
}

function getHighlightsForBlock(clauseKey, blockIndex, blockId = getBlockIdByIndex(clauseKey, blockIndex)) {
  return (state.ui.highlights || []).filter(
    (item) => blockReferenceMatches(item, clauseKey, blockIndex, blockId)
  );
}

function hasBlockHighlight(clauseKey, blockIndex, blockId = getBlockIdByIndex(clauseKey, blockIndex)) {
  return getHighlightsForBlock(clauseKey, blockIndex, blockId).some((item) => Number(item.rowIndex ?? -1) < 0);
}

function getHighlightedRowIndexes(clauseKey, blockIndex, block, blockId = getBlockIdByIndex(clauseKey, blockIndex)) {
  const localEntries = getHighlightsForBlock(clauseKey, blockIndex, blockId).filter(
    (item) => Number(item.rowIndex ?? -1) >= 0 && Number(item.cellIndex ?? -1) < 0
  );
  const globalRowEntries = (state.ui.highlights || []).filter(
    (item) =>
      item.clauseKey === clauseKey &&
      Number(item.blockIndex) < 0 &&
      Number(item.rowIndex ?? -1) >= 0 &&
      Number(item.cellIndex ?? -1) < 0
  );
  const entries = [...localEntries, ...globalRowEntries];
  const indexes = new Set(entries.map((item) => Number(item.rowIndex ?? -1)).filter((value) => value >= 0));
  const rowTexts = new Set();
  entries.forEach((item) => {
    buildHighlightRowVariants(item.rowText).forEach((variant) => rowTexts.add(variant));
  });
  if (!rowTexts.size) {
    return indexes;
  }
  const rows = Array.isArray(block.cells) && block.cells.length
    ? block.cells.map((row) => row.map((cell) => normalizeTableDisplayText(cell.text || "")))
    : (block.rows || []).map((row) => row.map((cell) => normalizeTableDisplayText(cell)));
  rows.forEach((row, rowIndex) => {
    const variants = buildRowVariants(row);
    if ([...variants].some((variant) => rowTexts.has(variant))) {
      indexes.add(rowIndex);
    }
  });
  return indexes;
}

function getHighlightedCellIndexes(clauseKey, blockIndex, rowIndex, blockId = getBlockIdByIndex(clauseKey, blockIndex)) {
  const block = getBlockByIndex(clauseKey, blockIndex);
  const row = Array.isArray(block?.cells) ? (block.cells[rowIndex] || []) : [];
  const rowCellIds = new Set(row.map((cell) => String(cell?.id || "").trim()).filter(Boolean));
  const entries = getHighlightsForBlock(clauseKey, blockIndex, blockId).filter(
    (item) =>
      Number(item.rowIndex ?? -1) === Number(rowIndex) &&
      Number(item.cellIndex ?? -1) >= 0
  );
  return new Set(
    entries
      .map((item) => {
        const highlightedCellId = String(item.cellId || "").trim();
        if (highlightedCellId && rowCellIds.size) {
          const matchedIndex = row.findIndex((cell) => String(cell?.id || "").trim() === highlightedCellId);
          return matchedIndex >= 0 ? matchedIndex : -1;
        }
        return Number(item.cellIndex ?? -1);
      })
      .filter((value) => value >= 0)
  );
}

function bindTreeEvents(scope = elements.treeContainer) {
  if (isBoardEditMode()) {
    initializeClauseEditors({
      scope,
      findNodeByKey,
      state,
      updateSelectedClauseActiveState,
      buildEditorHtmlFromBlocks,
      ensureBlocksHaveStableIds,
      updateSelectionStateFromEditorSelection,
      hideNodeMenu,
      showSelectionMenu,
      syncEditorHtmlToNode,
    });
  }
  scope.querySelectorAll("[data-action='toggle-node']").forEach((button) => {
    button.addEventListener("click", () => {
      const key = button.dataset.nodeKey;
      const expandedKeys = new Set(state.ui.expandedKeys);
      if (expandedKeys.has(key)) {
        expandedKeys.delete(key);
      } else {
        expandedKeys.add(key);
      }
      state.ui.expandedKeys = expandedKeys;
      persistSessionState();
      renderLoadedTree();
    });
  });

  scope.querySelectorAll("[data-action='toggle-loaded-spec']").forEach((button) => {
    button.addEventListener("click", () => {
      const specNo = button.dataset.specNo || "";
      const collapsed = new Set(state.ui.collapsedLoadedSpecs);
      if (collapsed.has(specNo)) {
        collapsed.delete(specNo);
      } else {
        collapsed.add(specNo);
      }
      state.ui.collapsedLoadedSpecs = collapsed;
      persistSessionState();
      renderLoadedTree();
    });
  });

  scope.querySelectorAll("[data-action='remove-node']").forEach((button) => {
    button.addEventListener("click", () => {
      const key = button.dataset.nodeKey;
      const target = findNodeByKey(key);
      if (!target) {
        return;
      }
      pruneNotesForNodeKey(key);
      pruneHighlightsForNodeKey(key);
      state.loadedRoots = removeNodeFromForest(state.loadedRoots, key);
      if (state.ui.focusedKey === key) {
        state.ui.focusedKey = "";
      }
      persistSessionState();
      renderLoadedTree();
      renderSelectedClauseList();
      renderClauseTree();
    });
  });

  scope.querySelectorAll("[data-action='focus-node']").forEach((button) => {
    button.addEventListener("click", () => {
      focusNode(button.dataset.nodeKey);
    });
  });

  scope.querySelectorAll(".tree-header").forEach((header) => {
    header.addEventListener("contextmenu", (event) => {
      if (isBoardViewMode()) {
        return;
      }
      const nodeKey = header.closest(".tree-node")?.dataset.nodeKey || "";
      const node = findNodeByKey(nodeKey);
      if (!node || !node.parentClauseId) {
        return;
      }
      event.preventDefault();
      hideSelectionMenu();
      showNodeMenu(event.clientX, event.clientY, nodeKey);
    });
  });

  scope.querySelectorAll(".tree-text").forEach((paragraph) => {
    paragraph.addEventListener("click", () => {
      updateSelectionStateFromElement(paragraph, "", false);
    });
    paragraph.addEventListener("contextmenu", (event) => {
      const selection = window.getSelection();
      const selectedText = selection ? selection.toString().trim() : "";
      event.preventDefault();
      hideNodeMenu();
      updateSelectionStateFromElement(paragraph, selectedText, Boolean(selectedText));
      showSelectionMenu(event.clientX, event.clientY);
    });
  });

  scope.querySelectorAll(".editor-selection-note-list, .editor-selection-note-list *").forEach((element) => {
    element.addEventListener("mousedown", (event) => {
      event.stopPropagation();
    });
    element.addEventListener("click", (event) => {
      event.stopPropagation();
    });
    element.addEventListener("contextmenu", (event) => {
      event.stopPropagation();
    });
  });

  scope.querySelectorAll(".docx-figure[data-block-type='image']").forEach((figure) => {
    figure.addEventListener("click", () => {
      figure.focus();
      updateSelectionStateFromElement(figure, "", false);
    });
  });

  scope.querySelectorAll("[data-action='translate-clause']").forEach((button) => {
    button.addEventListener("click", async () => {
      await runClauseTranslation(button.dataset.nodeKey || "");
    });
  });

  scope.querySelectorAll("[data-action='toggle-clause-notes']").forEach((button) => {
    button.addEventListener("click", () => {
      toggleClauseNotes(button.dataset.clauseKey || "");
    });
  });

  scope.querySelectorAll("[data-action='toggle-selection-notes']").forEach((button) => {
    button.addEventListener("click", () => {
      toggleSelectionNotes(
        button.dataset.clauseKey || "",
        Number(button.dataset.blockIndex || -1),
        Number(button.dataset.rowIndex || -1),
        Number(button.dataset.cellIndex || -1),
        button.dataset.blockId || "",
        button.dataset.cellId || ""
      );
    });
  });

  scope.querySelectorAll("[data-action='delete-note']").forEach((button) => {
    button.addEventListener("click", () => {
      deleteNote(button.dataset.noteId || "");
    });
  });

  scope.querySelectorAll("[data-action='edit-note-translation']").forEach((textarea) => {
    textarea.addEventListener("input", (event) => {
      updateNoteField(textarea.dataset.noteId || "", "translation", event.target.value);
    });
  });

}

function syncEditorHtmlToNode(nodeKey, html) {
  const nextBlocks = parseEditorHtmlToBlocks(html);
  const changed = updateNodeBlocks(nodeKey, (blocks) => {
    const current = JSON.stringify(blocks || []);
    const next = JSON.stringify(nextBlocks);
    if (current === next) {
      return blocks;
    }
    return nextBlocks;
  });
  if (!changed) {
    return;
  }
  persistSessionState();
  updateSelectionStateFromEditorSelection();
}

function handleTreeDeleteKeydown(event) {
  if (isBoardViewMode()) {
    return;
  }
  if (event.key !== "Backspace" && event.key !== "Delete") {
    return;
  }
  const target = event.target;
  if (target instanceof HTMLElement && target.closest(".clause-editor-host")) {
    return;
  }

  const focusedImage = document.activeElement?.closest?.(".docx-figure[data-block-type='image']");
  if (focusedImage && elements.treeContainer.contains(focusedImage)) {
    event.preventDefault();
    deleteImageBlockFromElement(focusedImage);
    return;
  }

  const selection = window.getSelection();
  if (!selection || !selection.rangeCount || selection.isCollapsed) {
    if (
      target instanceof HTMLInputElement ||
      target instanceof HTMLTextAreaElement ||
      target instanceof HTMLSelectElement ||
      (target instanceof HTMLElement && target.isContentEditable)
    ) {
      return;
    }
    return;
  }
  const range = selection.getRangeAt(0);
  if (!isRangeInsideTree(range)) {
    return;
  }

  const deletePlan = buildSelectionDeletePlan(range);
  if (!deletePlan) {
    return;
  }
  if (target instanceof HTMLElement && target.isContentEditable && (deletePlan.type === "paragraph-text" || deletePlan.type === "table-cell-text")) {
    return;
  }
  event.preventDefault();
  applySelectionDeletePlan(deletePlan);
  selection.removeAllRanges();
}

function isRangeInsideTree(range) {
  const startNode = range.startContainer?.nodeType === Node.TEXT_NODE ? range.startContainer.parentElement : range.startContainer;
  const endNode = range.endContainer?.nodeType === Node.TEXT_NODE ? range.endContainer.parentElement : range.endContainer;
  return Boolean(
    (startNode instanceof Node && elements.treeContainer.contains(startNode)) ||
    (endNode instanceof Node && elements.treeContainer.contains(endNode))
  );
}

function deleteImageBlockFromElement(element) {
  const clauseKey = element.dataset.clauseKey || "";
  const blockIndex = Number(element.dataset.blockIndex || -1);
  if (!clauseKey || blockIndex < 0) {
    return;
  }
  const changed = updateNodeBlocks(clauseKey, (blocks) => removeBlockAt(blocks, blockIndex));
  if (!changed) {
    return;
  }
  remapAnnotationsForBlockRemoval(clauseKey, blockIndex);
  clearTreeSelectionState();
  persistSessionState();
  rerenderLoadedNode(clauseKey);
}

function clearTreeSelectionState() {
  updateSelectionState("", "", "", -1, -1, -1, "", false);
  hideSelectionMenu();
}

function buildSelectionDeletePlan(range) {
  const paragraphs = getIntersectedElements(range, ".docx-paragraph[data-clause-key]");
  const cells = getIntersectedElements(range, ".table-cell-content[data-clause-key]");
  if (paragraphs.length && cells.length) {
    return {
      type: "remove-blocks",
      blockTargets: [
        ...paragraphs.map((element) => ({
          clauseKey: element.dataset.clauseKey || "",
          blockIndex: Number(element.dataset.blockIndex || -1),
        })),
        ...cells.map((element) => ({
          clauseKey: element.dataset.clauseKey || "",
          blockIndex: Number(element.dataset.blockIndex || -1),
        })),
      ],
    };
  }
  if (paragraphs.length === 1 && !cells.length) {
    return buildParagraphDeletePlan(range, paragraphs[0]);
  }
  if (cells.length) {
    return buildTableDeletePlan(range, cells);
  }
  if (paragraphs.length > 1) {
    return buildMultiParagraphDeletePlan(paragraphs);
  }
  return null;
}

function getIntersectedElements(range, selector) {
  return [...elements.treeContainer.querySelectorAll(selector)].filter((element) => {
    try {
      return range.intersectsNode(element);
    } catch (_error) {
      return false;
    }
  });
}

function buildParagraphDeletePlan(range, paragraph) {
  const clauseKey = paragraph.dataset.clauseKey || "";
  const blockIndex = Number(paragraph.dataset.blockIndex || -1);
  const offsets = getRangeOffsetsWithinElement(range, paragraph);
  if (!clauseKey || blockIndex < 0 || !offsets || offsets.end <= offsets.start) {
    return null;
  }
  return {
    type: "paragraph-text",
    clauseKey,
    blockIndex,
    start: offsets.start,
    end: offsets.end,
  };
}

function buildMultiParagraphDeletePlan(paragraphs) {
  const blockTargets = paragraphs
    .map((element) => ({
      clauseKey: element.dataset.clauseKey || "",
      blockIndex: Number(element.dataset.blockIndex || -1),
    }))
    .filter((item) => item.clauseKey && item.blockIndex >= 0);
  if (!blockTargets.length) {
    return null;
  }
  return { type: "remove-blocks", blockTargets };
}

function buildTableDeletePlan(range, cells) {
  const first = cells[0];
  const clauseKey = first.dataset.clauseKey || "";
  const blockIndex = Number(first.dataset.blockIndex || -1);
  const multipleBlocks = cells.some(
    (cell) => cell.dataset.clauseKey !== clauseKey || Number(cell.dataset.blockIndex || -1) !== blockIndex
  );
  if (multipleBlocks) {
    return {
      type: "remove-blocks",
      blockTargets: cells.map((cell) => ({
        clauseKey: cell.dataset.clauseKey || "",
        blockIndex: Number(cell.dataset.blockIndex || -1),
      })),
    };
  }
  const sameBlockCells = cells.filter(
    (cell) => cell.dataset.clauseKey === clauseKey && Number(cell.dataset.blockIndex || -1) === blockIndex
  );
  const allCells = [...elements.treeContainer.querySelectorAll(".table-cell-content[data-clause-key]")]
    .filter((cell) => cell.dataset.clauseKey === clauseKey && Number(cell.dataset.blockIndex || -1) === blockIndex);
  if (sameBlockCells.length === allCells.length) {
    return { type: "remove-blocks", blockTargets: [{ clauseKey, blockIndex }] };
  }

  const selectedByRow = groupCellsByRow(sameBlockCells);
  const allByRow = groupCellsByRow(allCells);
  const selectedRows = [...selectedByRow.keys()].filter((rowIndex) => {
    const selectedCols = selectedByRow.get(rowIndex) || new Set();
    const allCols = allByRow.get(rowIndex) || new Set();
    return selectedCols.size > 0 && selectedCols.size === allCols.size;
  });
  if (selectedRows.length) {
    return { type: "delete-table-rows", clauseKey, blockIndex, rowIndexes: selectedRows.sort((a, b) => b - a) };
  }

  const selectedByColumn = groupCellsByColumn(sameBlockCells);
  const allByColumn = groupCellsByColumn(allCells);
  const selectedColumns = [...selectedByColumn.keys()].filter((columnIndex) => {
    const selectedRowsForColumn = selectedByColumn.get(columnIndex) || new Set();
    const allRowsForColumn = allByColumn.get(columnIndex) || new Set();
    return selectedRowsForColumn.size > 0 && selectedRowsForColumn.size === allRowsForColumn.size;
  });
  if (selectedColumns.length) {
    return { type: "delete-table-columns", clauseKey, blockIndex, columnIndexes: selectedColumns.sort((a, b) => b - a) };
  }

  if (sameBlockCells.length === 1) {
    const textHolder = sameBlockCells[0].querySelector(".table-cell-text");
    if (textHolder) {
      const offsets = getRangeOffsetsWithinElement(range, textHolder);
      if (offsets && offsets.end > offsets.start) {
        return {
          type: "table-cell-text",
          clauseKey,
          blockIndex,
          rowIndex: Number(sameBlockCells[0].dataset.rowIndex || -1),
          cellIndex: Number(sameBlockCells[0].dataset.cellIndex || -1),
          start: offsets.start,
          end: offsets.end,
        };
      }
    }
  }
  return { type: "remove-blocks", blockTargets: [{ clauseKey, blockIndex }] };
}

function groupCellsByRow(cells) {
  return cells.reduce((map, cell) => {
    const rowIndex = Number(cell.dataset.rowIndex || -1);
    const cellIndex = Number(cell.dataset.cellIndex || -1);
    if (rowIndex < 0 || cellIndex < 0) {
      return map;
    }
    const existing = map.get(rowIndex) || new Set();
    existing.add(cellIndex);
    map.set(rowIndex, existing);
    return map;
  }, new Map());
}

function groupCellsByColumn(cells) {
  return cells.reduce((map, cell) => {
    const columnIndex = Number(cell.dataset.colIndex || -1);
    const rowIndex = Number(cell.dataset.rowIndex || -1);
    if (columnIndex < 0 || rowIndex < 0) {
      return map;
    }
    const existing = map.get(columnIndex) || new Set();
    existing.add(rowIndex);
    map.set(columnIndex, existing);
    return map;
  }, new Map());
}

function getRangeOffsetsWithinElement(range, element) {
  try {
    const startRange = range.cloneRange();
    startRange.selectNodeContents(element);
    startRange.setEnd(range.startContainer, range.startOffset);
    const endRange = range.cloneRange();
    endRange.selectNodeContents(element);
    endRange.setEnd(range.endContainer, range.endOffset);
    return {
      start: startRange.toString().length,
      end: endRange.toString().length,
    };
  } catch (_error) {
    return null;
  }
}

function applySelectionDeletePlan(plan) {
  if (plan.type === "paragraph-text") {
    deleteParagraphText(plan);
    return;
  }
  if (plan.type === "table-cell-text") {
    deleteTableCellText(plan);
    return;
  }
  if (plan.type === "delete-table-rows") {
    deleteSelectedTableRows(plan);
    return;
  }
  if (plan.type === "delete-table-columns") {
    deleteSelectedTableColumns(plan);
    return;
  }
  if (plan.type === "remove-blocks") {
    removeSelectedBlocks(plan.blockTargets);
  }
}

function deleteParagraphText(plan) {
  let removedBlock = false;
  const changed = updateNodeBlocks(plan.clauseKey, (blocks) => {
    const block = blocks[plan.blockIndex];
    if (!block || block.type !== "paragraph") {
      return blocks;
    }
    const text = String(block.text || "");
    const nextText = `${text.slice(0, plan.start)}${text.slice(plan.end)}`;
    if (!nextText.trim()) {
      removedBlock = true;
      return removeBlockAt(blocks, plan.blockIndex);
    }
    return blocks.map((item, index) => (index === plan.blockIndex ? { ...item, text: nextText } : item));
  });
  if (!changed) {
    return;
  }
  if (removedBlock) {
    remapAnnotationsForBlockRemoval(plan.clauseKey, plan.blockIndex);
  }
  clearTreeSelectionState();
  persistSessionState();
  rerenderLoadedNode(plan.clauseKey);
}

function deleteTableCellText(plan) {
  const changed = updateNodeBlocks(plan.clauseKey, (blocks) => {
    const block = blocks[plan.blockIndex];
    if (!block || block.type !== "table") {
      return blocks;
    }
    if (Array.isArray(block.cells) && block.cells.length) {
      const nextCells = block.cells.map((row, rowIndex) =>
        row.map((cell, cellIndex) => {
          if (rowIndex !== plan.rowIndex || cellIndex !== plan.cellIndex) {
            return cell;
          }
          const text = String(cell.text || "");
          return { ...cell, text: `${text.slice(0, plan.start)}${text.slice(plan.end)}` };
        })
      );
      return blocks.map((item, index) => (index === plan.blockIndex ? { ...item, cells: nextCells } : item));
    }
    const nextRows = (block.rows || []).map((row, rowIndex) =>
      row.map((cell, cellIndex) => {
        if (rowIndex !== plan.rowIndex || cellIndex !== plan.cellIndex) {
          return cell;
        }
        const text = String(cell || "");
        return `${text.slice(0, plan.start)}${text.slice(plan.end)}`;
      })
    );
    return blocks.map((item, index) => (index === plan.blockIndex ? { ...item, rows: nextRows } : item));
  });
  if (!changed) {
    return;
  }
  clearTreeSelectionState();
  persistSessionState();
  rerenderLoadedNode(plan.clauseKey);
}

function deleteSelectedTableRows(plan) {
  let removedBlock = false;
  const changed = updateNodeBlocks(plan.clauseKey, (blocks) => {
    const block = blocks[plan.blockIndex];
    if (!block || block.type !== "table") {
      return blocks;
    }
    let nextBlock = block;
    for (const rowIndex of plan.rowIndexes) {
      nextBlock = removeTableRow(nextBlock, rowIndex);
      if (!nextBlock) {
        removedBlock = true;
        return removeBlockAt(blocks, plan.blockIndex);
      }
    }
    return blocks.map((item, index) => (index === plan.blockIndex ? nextBlock : item));
  });
  if (!changed) {
    return;
  }
  if (removedBlock) {
    remapAnnotationsForBlockRemoval(plan.clauseKey, plan.blockIndex);
  } else {
    plan.rowIndexes.forEach((rowIndex) => remapAnnotationsForRowRemoval(plan.clauseKey, plan.blockIndex, rowIndex));
  }
  clearTreeSelectionState();
  persistSessionState();
  rerenderLoadedNode(plan.clauseKey);
}

function deleteSelectedTableColumns(plan) {
  let removedBlock = false;
  const changed = updateNodeBlocks(plan.clauseKey, (blocks) => {
    const block = blocks[plan.blockIndex];
    if (!block || block.type !== "table") {
      return blocks;
    }
    let nextBlock = block;
    for (const columnIndex of plan.columnIndexes) {
      nextBlock = removeTableColumn(nextBlock, columnIndex);
      if (!nextBlock) {
        removedBlock = true;
        return removeBlockAt(blocks, plan.blockIndex);
      }
    }
    return blocks.map((item, index) => (index === plan.blockIndex ? nextBlock : item));
  });
  if (!changed) {
    return;
  }
  if (removedBlock) {
    remapAnnotationsForBlockRemoval(plan.clauseKey, plan.blockIndex);
  } else {
    plan.columnIndexes.forEach((columnIndex) => remapAnnotationsForColumnRemoval(plan.clauseKey, plan.blockIndex, columnIndex));
  }
  clearTreeSelectionState();
  persistSessionState();
  rerenderLoadedNode(plan.clauseKey);
}

function removeSelectedBlocks(blockTargets) {
  const grouped = blockTargets.reduce((map, item) => {
    const key = item.clauseKey;
    const existing = map.get(key) || [];
    existing.push(Number(item.blockIndex));
    map.set(key, existing);
    return map;
  }, new Map());

  grouped.forEach((indexes, clauseKey) => {
    const uniqueIndexes = [...new Set(indexes)].sort((a, b) => b - a);
    const changed = updateNodeBlocks(clauseKey, (blocks) => {
      let nextBlocks = blocks;
      uniqueIndexes.forEach((blockIndex) => {
        nextBlocks = removeBlockAt(nextBlocks, blockIndex);
      });
      return nextBlocks;
    });
    if (!changed) {
      return;
    }
    uniqueIndexes.forEach((blockIndex) => remapAnnotationsForBlockRemoval(clauseKey, blockIndex));
  });

  clearTreeSelectionState();
  persistSessionState();
  rerenderLoadedNodes([...grouped.keys()]);
}

function findNodeByKey(key, nodes = state.loadedRoots) {
  for (const node of nodes) {
    if (node.key === key) {
      return node;
    }
    const child = findNodeByKey(key, node.children || []);
    if (child) {
      return child;
    }
  }
  return null;
}

function removeNodeFromForest(nodes, key) {
  return nodes
    .filter((node) => node.key !== key)
    .map((node) => ({
      ...node,
      children: removeNodeFromForest(node.children || [], key),
    }));
}

function updateNodeInForest(nodes, key, updater) {
  return (nodes || []).map((node) => {
    if (node.key === key) {
      return updater(node);
    }
    if (!node.children?.length) {
      return node;
    }
    return {
      ...node,
      children: updateNodeInForest(node.children || [], key, updater),
    };
  });
}

function updateNodeBlocks(nodeKey, transform) {
  let changed = false;
  state.loadedRoots = updateNodeInForest(state.loadedRoots, nodeKey, (node) => {
    const currentBlocks = ensureBlocksHaveStableIds(Array.isArray(node.blocks) ? node.blocks : []);
    const transformedBlocks = transform(currentBlocks);
    if (transformedBlocks === currentBlocks) {
      return node;
    }
    const nextBlocks = ensureBlocksHaveStableIds(Array.isArray(transformedBlocks) ? transformedBlocks : []);
    changed = true;
    return {
      ...node,
      blocks: nextBlocks,
      text: deriveNodeTextFromBlocks(nextBlocks),
    };
  });
  if (changed) {
    syncClauseAnnotationBlockReferences(nodeKey);
  }
  return changed;
}

function remapAnnotationsForBlockRemoval(clauseKey, blockIndex) {
  state.ui.notes = (state.ui.notes || []).flatMap((note) => {
    if (note.type !== "selection" || note.clauseKey !== clauseKey) {
      return [note];
    }
    if (String(note.blockId || "").trim()) {
      return [note];
    }
    const currentBlockIndex = Number(note.blockIndex ?? -1);
    if (currentBlockIndex === blockIndex) {
      return [];
    }
    if (currentBlockIndex > blockIndex) {
      return [{ ...note, blockIndex: currentBlockIndex - 1 }];
    }
    return [note];
  });
  state.ui.highlights = (state.ui.highlights || []).flatMap((item) => {
    if (item.clauseKey !== clauseKey) {
      return [item];
    }
    if (String(item.blockId || "").trim()) {
      return [item];
    }
    const currentBlockIndex = Number(item.blockIndex ?? -1);
    if (currentBlockIndex === blockIndex) {
      return [];
    }
    if (currentBlockIndex > blockIndex) {
      return [{ ...item, blockIndex: currentBlockIndex - 1 }];
    }
    return [item];
  });
}

function remapAnnotationsForRowRemoval(clauseKey, blockIndex, rowIndex) {
  const blockId = getBlockIdByIndex(clauseKey, blockIndex);
  state.ui.notes = (state.ui.notes || []).flatMap((note) => {
    if (note.type !== "selection" || !blockReferenceMatches(note, clauseKey, blockIndex, blockId)) {
      return [note];
    }
    if (String(note.cellId || "").trim()) {
      return [note];
    }
    const currentRowIndex = Number(note.rowIndex ?? -1);
    if (currentRowIndex < 0) {
      return [note];
    }
    if (currentRowIndex === rowIndex) {
      return [];
    }
    if (currentRowIndex > rowIndex) {
      return [{ ...note, rowIndex: currentRowIndex - 1 }];
    }
    return [note];
  });
  state.ui.highlights = (state.ui.highlights || []).flatMap((item) => {
    if (!blockReferenceMatches(item, clauseKey, blockIndex, blockId)) {
      return [item];
    }
    if (String(item.cellId || "").trim()) {
      return [item];
    }
    const currentRowIndex = Number(item.rowIndex ?? -1);
    if (currentRowIndex < 0) {
      return [item];
    }
    if (currentRowIndex === rowIndex) {
      return [];
    }
    if (currentRowIndex > rowIndex) {
      return [{ ...item, rowIndex: currentRowIndex - 1 }];
    }
    return [item];
  });
}

function remapAnnotationsForColumnRemoval(clauseKey, blockIndex, columnIndex) {
  const blockId = getBlockIdByIndex(clauseKey, blockIndex);
  state.ui.notes = (state.ui.notes || []).flatMap((note) => {
    if (note.type !== "selection" || !blockReferenceMatches(note, clauseKey, blockIndex, blockId)) {
      return [note];
    }
    if (String(note.cellId || "").trim()) {
      return [note];
    }
    const currentCellIndex = Number(note.cellIndex ?? -1);
    if (currentCellIndex < 0) {
      return [note];
    }
    if (currentCellIndex === columnIndex) {
      return [];
    }
    if (currentCellIndex > columnIndex) {
      return [{ ...note, cellIndex: currentCellIndex - 1 }];
    }
    return [note];
  });
  state.ui.highlights = (state.ui.highlights || []).flatMap((item) => {
    if (!blockReferenceMatches(item, clauseKey, blockIndex, blockId)) {
      return [item];
    }
    if (String(item.cellId || "").trim()) {
      return [item];
    }
    const currentCellIndex = Number(item.cellIndex ?? -1);
    if (currentCellIndex < 0) {
      return [item];
    }
    if (currentCellIndex === columnIndex) {
      return [];
    }
    if (currentCellIndex > columnIndex) {
      return [{ ...item, cellIndex: currentCellIndex - 1 }];
    }
    return [item];
  });
}

function findLoadedAncestor(specNo, clauseId) {
  const clausePath = String(clauseId || "").split(".").filter(Boolean);
  for (let index = clausePath.length - 1; index >= 0; index -= 1) {
    const candidateId = clausePath.slice(0, index + 1).join(".");
    const candidate = findNodeByKey(`${specNo}:${candidateId}`);
    if (candidate) {
      return candidate;
    }
  }
  return null;
}

function isClausePathPrefix(ancestorPath, descendantPath) {
  const left = ancestorPath || [];
  const right = descendantPath || [];
  if (left.length > right.length) {
    return false;
  }
  return left.every((part, index) => part === right[index]);
}

function mergeLoadedRoot(roots, subtree) {
  const prunedRoots = (roots || []).filter(
    (root) => !(root.specNo === subtree.specNo && isClausePathPrefix(subtree.clausePath || [], root.clausePath || []))
  );
  return [...prunedRoots, subtree];
}

function focusNode(key) {
  hideNodeMenu();
  const node = findNodeByKey(key);
  if (node?.specNo) {
    const collapsedLoadedSpecs = new Set(state.ui.collapsedLoadedSpecs || []);
    collapsedLoadedSpecs.delete(node.specNo);
    state.ui.collapsedLoadedSpecs = collapsedLoadedSpecs;
  }
  expandNodePath(key);
  state.ui.focusedKey = key;
  state.ui.viewportKey = key;
  persistSessionState();
  renderLoadedTree();
  updateSelectedClauseActiveState();
  ensureSelectedClauseVisible();
  window.setTimeout(() => {
    const element = document.getElementById(`node-${escapeKey(key)}`);
    element?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, 0);
}

async function addParentClause(nodeKey) {
  if (state.ui.busy && state.ui.busy !== SPECBOT_QUERY_BUSY_LABEL) {
    setMessage(`다른 작업이 진행 중입니다: ${state.ui.busy}`, true);
    return;
  }
  const node = findNodeByKey(nodeKey);
  if (!node) {
    setMessage("절 정보를 찾을 수 없습니다.", true);
    return;
  }
  if (!node.parentClauseId) {
    setMessage(`${node.clauseId} 절은 최상위 절입니다.`, true);
    return;
  }
  const parentKey = `${node.specNo}:${node.parentClauseId}`;
  const loadedParent = findNodeByKey(parentKey);
  if (loadedParent) {
    focusNode(parentKey);
    setMessage(`상위 절 ${node.parentClauseId}는 이미 로드되어 있습니다.`, false);
    return;
  }
  const loaded = await loadClauseWithSpec(node.specNo, node.parentClauseId);
  if (loaded) {
    setMessage(`${node.parentClauseId} 상위 절을 추가했습니다.`, false);
  }
}

function renderSelectedClauseList() {
  const roots = state.loadedRoots || [];
  elements.selectedClauseCount.textContent = String(countNodes(roots));
  if (!roots.length) {
    elements.selectedClauseList.innerHTML = '<div class="muted">추가된 절이 아직 없습니다.</div>';
    return;
  }
  const grouped = groupRootsBySpec(roots);
  elements.selectedClauseList.innerHTML = Object.entries(grouped)
    .map(
      ([specNo, nodes]) => `
        <section class="selected-spec-group">
          <div class="selected-spec-title">
            <button class="selected-spec-toggle" data-action="toggle-selected-spec" data-spec-no="${escapeHtml(specNo)}">
              ${state.ui.collapsedSpecs.has(specNo) ? "+" : "−"}
            </button>
            <span>${escapeHtml(specNo)}</span>
          </div>
          ${state.ui.collapsedSpecs.has(specNo) ? "" : nodes.map((node) => renderSelectedClauseCard(node, 0)).join("")}
        </section>
      `
    )
    .join("");
  elements.selectedClauseList.querySelectorAll("[data-action='toggle-selected-spec']").forEach((button) => {
    button.addEventListener("click", () => {
      toggleSelectedSpec(button.dataset.specNo);
    });
  });
  elements.selectedClauseList.querySelectorAll("[data-action='focus-selected']").forEach((button) => {
    button.addEventListener("click", () => {
      focusNode(button.dataset.nodeKey);
    });
  });
  updateSelectedClauseActiveState();
  ensureSelectedClauseVisible();
}

function updateSelectedClauseActiveState() {
  elements.selectedClauseList.querySelectorAll(".selected-clause-row").forEach((row) => {
    const key = row.dataset.selectedKey || "";
    const isActive = key === state.ui.viewportKey || key === state.ui.focusedKey;
    row.classList.toggle("active", isActive);
  });
}

function renderSelectedClauseCard(node, depth) {
  const isActive = node.key === state.ui.viewportKey || node.key === state.ui.focusedKey;
  return `
    <div class="selected-clause-row ${isActive ? "active" : ""}" data-selected-key="${escapeHtml(node.key)}" style="margin-left:${depth * 12}px">
      <span class="selected-clause-bullet">-</span>
      <button class="selected-clause-link" data-action="focus-selected" data-node-key="${escapeHtml(node.key)}">
        ${escapeHtml(node.clauseId)} ${escapeHtml(node.clauseTitle)}
      </button>
    </div>
    ${(node.children || []).map((child) => renderSelectedClauseCard(child, depth + 1)).join("")}
  `;
}

function groupRootsBySpec(roots) {
  return [...roots].sort(compareLoadedNodes).reduce((groups, node) => {
    const next = { ...groups };
    const existing = next[node.specNo] || [];
    next[node.specNo] = [...existing, node];
    return next;
  }, {});
}

function compareLoadedNodes(left, right) {
  const specCompare = compareMixedToken(String(left.specNo || ""), String(right.specNo || ""));
  if (specCompare !== 0) {
    return specCompare;
  }
  const leftPath = left.clausePath || [left.clauseId || ""];
  const rightPath = right.clausePath || [right.clauseId || ""];
  const pathLength = Math.max(leftPath.length, rightPath.length);
  for (let index = 0; index < pathLength; index += 1) {
    const leftPart = leftPath[index] ?? "";
    const rightPart = rightPath[index] ?? "";
    const partCompare = compareClausePart(leftPart, rightPart);
    if (partCompare !== 0) {
      return partCompare;
    }
  }
  return 0;
}

function compareSpecbotHits(left, right) {
  const specCompare = compareMixedToken(String(left.specNo || ""), String(right.specNo || ""));
  if (specCompare !== 0) {
    return specCompare;
  }
  const leftPath = left.clausePath || [left.clauseId || ""];
  const rightPath = right.clausePath || [right.clauseId || ""];
  const pathLength = Math.max(leftPath.length, rightPath.length);
  for (let index = 0; index < pathLength; index += 1) {
    const partCompare = compareClausePart(leftPath[index] ?? "", rightPath[index] ?? "");
    if (partCompare !== 0) {
      return partCompare;
    }
  }
  return 0;
}

function compareClausePart(left, right) {
  const leftTokens = String(left).split(".");
  const rightTokens = String(right).split(".");
  const length = Math.max(leftTokens.length, rightTokens.length);
  for (let index = 0; index < length; index += 1) {
    const tokenCompare = compareMixedToken(leftTokens[index] ?? "", rightTokens[index] ?? "");
    if (tokenCompare !== 0) {
      return tokenCompare;
    }
  }
  return 0;
}

function compareMixedToken(left, right) {
  const leftMatch = String(left).match(/^(\d+)(.*)$/);
  const rightMatch = String(right).match(/^(\d+)(.*)$/);
  if (leftMatch && rightMatch) {
    const numberCompare = Number(leftMatch[1]) - Number(rightMatch[1]);
    if (numberCompare !== 0) {
      return numberCompare;
    }
    return leftMatch[2].localeCompare(rightMatch[2]);
  }
  return String(left).localeCompare(String(right), undefined, { numeric: true });
}

function isCaptionParagraph(text, block = null) {
  const format = block?.format || {};
  const styleName = String(format.styleName || "").trim().toUpperCase();
  const alignment = Number(format.alignment);
  if (styleName === "TF") {
    return true;
  }
  if (Number.isFinite(alignment) && alignment === 1) {
    return true;
  }
  return /^(Figure|Table)\s+[A-Za-z0-9.\-]+:\s+\S+/.test(String(text).trim());
}

function hasDocxParagraphFormat(block) {
  const format = block?.format || {};
  return (
    Number.isFinite(Number(format.leftIndentPt)) ||
    Number.isFinite(Number(format.textIndentPt)) ||
    Number.isFinite(Number(format.leftIndentPx)) ||
    Number.isFinite(Number(format.textIndentPx))
  );
}

function getParagraphClass(text, block = null) {
  const value = String(text).trim();
  const fallbackClass = hasDocxParagraphFormat(block) ? "" : " docx-fallback";
  if (isCaptionParagraph(value, block)) {
    return "tree-text docx-paragraph docx-caption";
  }
  if (/^NOTE\s*:/i.test(value)) {
    return `tree-text docx-paragraph docx-note${fallbackClass}`;
  }
  if (/^(EXAMPLE|Examples?)\s*:/i.test(value)) {
    return `tree-text docx-paragraph docx-example${fallbackClass}`;
  }
  if (/^(WARNING|CAUTION)\s*:/i.test(value)) {
    return `tree-text docx-paragraph docx-warning${fallbackClass}`;
  }
  if (/^(Annex|APPENDIX)\b/i.test(value)) {
    return "tree-text docx-paragraph docx-annex";
  }
  if (/^(?:[-*•]|[A-Za-z]\)|\d+[A-Za-z]+\)|\d+\)|\d+[A-Za-z]+\.\s+|\d+\.\s+)/.test(value)) {
    return `tree-text docx-paragraph docx-list${fallbackClass}`;
  }
  return "tree-text docx-paragraph";
}

function toggleSelectedSpec(specNo) {
  const collapsedSpecs = new Set(state.ui.collapsedSpecs);
  if (collapsedSpecs.has(specNo)) {
    collapsedSpecs.delete(specNo);
  } else {
    collapsedSpecs.add(specNo);
  }
  state.ui.collapsedSpecs = collapsedSpecs;
  persistSessionState();
  renderSelectedClauseList();
}

function syncViewportSelection() {
  const nodes = [...elements.treeContainer.querySelectorAll(".tree-node")];
  if (!nodes.length) {
    if (state.ui.viewportKey) {
      state.ui.viewportKey = "";
      updateSelectedClauseActiveState();
    }
    return;
  }
  const containerRect = elements.treeContainer.getBoundingClientRect();
  let bestKey = "";
  let bestDistance = Infinity;
  nodes.forEach((node) => {
    const rect = node.getBoundingClientRect();
    const visible = rect.bottom >= containerRect.top && rect.top <= containerRect.bottom;
    if (!visible) {
      return;
    }
    const distance = Math.abs(rect.top - containerRect.top - 24);
    if (distance < bestDistance) {
      bestDistance = distance;
      bestKey = node.dataset.nodeKey || "";
    }
  });
  if (bestKey && bestKey !== state.ui.viewportKey) {
    state.ui.viewportKey = bestKey;
    persistSessionState();
    updateSelectedClauseActiveState();
    ensureSelectedClauseVisible();
  }
}

function ensureSelectedClauseVisible() {
  const active = elements.selectedClauseList.querySelector(".selected-clause-row.active");
  active?.scrollIntoView({ block: "nearest" });
}

function handleSelectionChange() {
  if (updateSelectionStateFromEditorSelection()) {
    return;
  }
  const selection = window.getSelection();
  const text = selection ? selection.toString().trim() : "";
  if (!text) {
    updateSelectionState("", "", "", -1, -1, -1, "", false);
    hideSelectionMenu();
    return;
  }
  const anchorElement = selection.anchorNode?.parentElement?.closest(".tree-text");
  if (!anchorElement) {
    return;
  }
  updateSelectionStateFromElement(anchorElement, text, true);
}

function updateSelectionStateFromEditorSelection(editor = null) {
  const host = getEditorSelectionHost(editor);
  if (!(host instanceof HTMLElement)) {
    return false;
  }
  const nodeKey = host.dataset.editorNodeKey || "";
  if (!nodeKey) {
    return false;
  }
  const selectedCells = getSelectedEditorTableCells(host);
  if (selectedCells.length) {
    return updateSelectionStateFromEditorTableSelection(nodeKey, host, selectedCells);
  }
  const selection = window.getSelection();
  if (!selection || !selection.rangeCount) {
    return false;
  }
  if (!host.contains(selection.anchorNode) && !host.contains(selection.focusNode)) {
    return false;
  }
  const topLevelBlocks = [...host.children];
  const focusElement = resolveEditorSelectionElement(selection, host);
  const blockElement = focusElement ? findTopLevelEditorBlock(focusElement, host) : null;
  const blockIndex = blockElement ? topLevelBlocks.indexOf(blockElement) : -1;
  const blockId = blockElement instanceof HTMLElement ? String(blockElement.getAttribute("data-editor-block-id") || "") : "";
  let rowIndex = -1;
  let cellIndex = -1;
  let cellId = "";
  let rowText = "";
  if (focusElement) {
    const cell = focusElement.closest("td, th");
    if (cell && blockElement?.tagName.toLowerCase() === "table") {
      const row = cell.closest("tr");
      const rows = [...blockElement.querySelectorAll("tr")];
      rowIndex = row ? rows.indexOf(row) : -1;
      cellIndex = row ? [...row.children].filter((item) => /^(TD|TH)$/.test(item.tagName)).indexOf(cell) : -1;
      cellId = String(cell.getAttribute("data-editor-cell-id") || "").trim();
      rowText = normalizeRowText(
        row ? [...row.children].filter((item) => /^(TD|TH)$/.test(item.tagName)).map((item) => item.textContent || "") : []
      );
    } else if (blockElement) {
      rowText = normalizeEditorText(blockElement.textContent || "");
    }
  }
  updateSelectionState(
    selection.toString().trim(),
    nodeKey,
    getLabelForKey(nodeKey),
    blockIndex,
    rowIndex,
    cellIndex,
    rowText,
    !selection.isCollapsed && Boolean(selection.toString().trim()),
    blockId,
    cellId
  );
  return true;
}

function getEditorSelectionHost(editor = null) {
  const editorElement = typeof editor?.getElement === "function" ? editor.getElement() : editor?.targetElm;
  if (editorElement instanceof HTMLElement && editorElement.matches(".clause-editor-host[data-editor-node-key]")) {
    return editorElement;
  }
  const selection = window.getSelection();
  const anchorParent = selection?.anchorNode?.nodeType === Node.TEXT_NODE
    ? selection.anchorNode.parentElement
    : selection?.anchorNode;
  const focusParent = selection?.focusNode?.nodeType === Node.TEXT_NODE
    ? selection.focusNode.parentElement
    : selection?.focusNode;
  return anchorParent instanceof Element
    ? anchorParent.closest(".clause-editor-host[data-editor-node-key]")
    : focusParent instanceof Element
      ? focusParent.closest(".clause-editor-host[data-editor-node-key]")
      : null;
}

function getSelectedEditorTableCells(host) {
  if (!(host instanceof HTMLElement)) {
    return [];
  }
  return [...host.querySelectorAll('td[data-mce-selected="1"], th[data-mce-selected="1"]')];
}

function updateSelectionStateFromEditorTableSelection(nodeKey, host, selectedCells) {
  const firstCell = selectedCells[0];
  const blockElement = firstCell ? findTopLevelEditorBlock(firstCell, host) : null;
  if (!(blockElement instanceof HTMLElement) || blockElement.tagName.toLowerCase() !== "table") {
    return false;
  }
  const topLevelBlocks = [...host.children];
  const blockIndex = topLevelBlocks.indexOf(blockElement);
  const blockId = String(blockElement.getAttribute("data-editor-block-id") || "");
  const rowMap = new Map();
  const selectedTexts = [];

  selectedCells.forEach((cell) => {
    const row = cell.closest("tr");
    if (!(row instanceof HTMLTableRowElement)) {
      return;
    }
    const rowIndex = [...blockElement.querySelectorAll("tr")].indexOf(row);
    if (rowIndex < 0) {
      return;
    }
    const cellsInRow = [...row.children].filter((item) => /^(TD|TH)$/.test(item.tagName));
    const cellIndex = cellsInRow.indexOf(cell);
    if (cellIndex < 0) {
      return;
    }
    const entry = rowMap.get(rowIndex) || { cellIndexes: new Set(), cellIds: new Set(), rowText: "" };
    entry.cellIndexes.add(cellIndex);
    const cellId = String(cell.getAttribute("data-editor-cell-id") || "").trim();
    if (cellId) {
      entry.cellIds.add(cellId);
    }
    entry.rowText = normalizeRowText(cellsInRow.map((item) => item.textContent || ""));
    rowMap.set(rowIndex, entry);
    const cellText = normalizeEditorText(cell.textContent || "");
    if (cellText) {
      selectedTexts.push(cellText);
    }
  });

  const rowIndexes = [...rowMap.keys()].sort((left, right) => left - right);
  const singleRow = rowIndexes.length === 1 ? rowIndexes[0] : -1;
  const singleRowEntry = singleRow >= 0 ? rowMap.get(singleRow) : null;
  const singleCell =
    singleRowEntry && singleRowEntry.cellIndexes.size === 1 ? [...singleRowEntry.cellIndexes][0] : -1;
  const singleCellId =
    singleRowEntry && singleRowEntry.cellIds.size === 1 ? [...singleRowEntry.cellIds][0] : "";
  const rowText = singleRowEntry?.rowText || "";
  const selectionText = selectedTexts.join(" | ").trim() || rowText || normalizeEditorText(blockElement.textContent || "");

  updateSelectionState(
    selectionText,
    nodeKey,
    getLabelForKey(nodeKey),
    blockIndex,
    singleRow,
    singleCell,
    rowText,
    selectedCells.length > 0,
    blockId,
    singleCellId
  );
  return true;
}

function resolveEditorSelectionElement(selection, host) {
  const range = selection.rangeCount ? selection.getRangeAt(0) : null;
  const candidates = [
    range?.commonAncestorContainer,
    selection.focusNode,
    selection.anchorNode,
  ];
  for (const candidate of candidates) {
    const element = candidate?.nodeType === Node.TEXT_NODE ? candidate.parentElement : candidate;
    if (element instanceof Element && host.contains(element)) {
      return element;
    }
  }
  return host;
}

function findTopLevelEditorBlock(element, host) {
  let current = element;
  while (current && current.parentElement && current.parentElement !== host) {
    current = current.parentElement;
  }
  return current instanceof HTMLElement && current.parentElement === host ? current : null;
}

function updateSelectionState(text, clauseKey, clauseLabel, blockIndex = -1, rowIndex = -1, cellIndex = -1, rowText = "", hasSelection = false, blockId = "", cellId = "") {
  state.ui.selection = { text, clauseKey, clauseLabel, blockId, blockIndex, rowIndex, cellIndex, cellId, rowText, hasSelection };
}

function updateSelectionStateFromElement(element, text = "", hasSelection = false) {
  if (!element) {
    updateSelectionState("", "", "", -1, -1, -1, "", false);
    return;
  }
  updateSelectionState(
    text,
    element.dataset.clauseKey || "",
    getLabelForKey(element.dataset.clauseKey || ""),
    Number(element.dataset.blockIndex || -1),
    Number(element.dataset.rowIndex || -1),
    Number(element.dataset.cellIndex || -1),
    element.dataset.rowText || "",
    hasSelection,
    element.dataset.blockId || "",
    element.dataset.cellId || ""
  );
}

function getLabelForKey(key) {
  const node = findNodeByKey(key);
  return node ? `${node.specNo} / ${node.clauseId} ${node.clauseTitle}` : "";
}

function showSelectionMenu(x, y) {
  const hasSelection = Boolean(state.ui.selection?.hasSelection && state.ui.selection?.text);
  const translateButton = elements.selectionMenu.querySelector("[data-action='translate-selection']");
  if (translateButton) {
    translateButton.disabled = !hasSelection;
  }
  elements.selectionMenu.style.left = `${x}px`;
  elements.selectionMenu.style.top = `${y}px`;
  elements.selectionMenu.classList.remove("hidden");
}

function hideSelectionMenu() {
  elements.selectionMenu.classList.add("hidden");
}

async function runSelectionAction(targetLanguage = "ko") {
  if (!beginBusy("선택 메모 번역 중입니다.")) {
    return;
  }
  const text = state.ui.selection.text;
  if (!text) {
    endBusy();
    setMessage("번역할 텍스트를 먼저 선택하세요.", true);
    return;
  }
  if (String(text).length > TRANSLATION_CHUNK_LIMIT) {
    endBusy();
    setMessage(`선택 메모는 ${TRANSLATION_CHUNK_LIMIT}자 이하만 번역할 수 있습니다. 범위를 줄여 주세요.`, true);
    return;
  }
  try {
    await createTranslatedNote({
      type: "selection",
      clauseKey: state.ui.selection.clauseKey,
      blockIndex: state.ui.selection.blockIndex,
      rowIndex: state.ui.selection.rowIndex,
      cellIndex: state.ui.selection.cellIndex,
      cellId: state.ui.selection.cellId,
      rowText: state.ui.selection.rowText,
      sourceText: text,
      clauseLabel: state.ui.selection.clauseLabel,
      targetLanguage,
    });
  } finally {
    endBusy();
  }
}

async function runClauseTranslation(clauseKey) {
  if (!beginBusy("절 번역 중입니다.")) {
    return;
  }
  const node = findNodeByKey(clauseKey);
  const translationNodes = collectTranslationNodes(node);
  if (!translationNodes.length) {
    endBusy();
    setMessage("번역할 절 본문을 찾을 수 없습니다.", true);
    return;
  }
  const estimatedRequests = translationNodes.reduce((total, item) => total + Number(item.requestCount || 0), 0);
  if (estimatedRequests >= 10) {
    endBusy();
    openNoticeModal(
      `예상 번역 요청이 ${estimatedRequests}개라 한 번에 진행할 수 없습니다. 긴 절은 여러 요청으로 분할됩니다. 예상 요청 수가 10개 미만이 되도록 범위를 줄여 주세요.`
    );
    return;
  }

  state.ui.translationJob = {
    rootKey: clauseKey,
    totalRequests: estimatedRequests,
    completedRequests: 0,
    currentLabel: getLabelForKey(clauseKey),
  };
  renderTranslationStatus();

  try {
    let completedRequests = 0;
    for (let index = 0; index < translationNodes.length; index += 1) {
      const currentNode = translationNodes[index];
      state.ui.translationJob = {
        ...state.ui.translationJob,
        completedRequests,
        currentLabel: getLabelForKey(currentNode.key),
      };
      renderTranslationStatus();
      await createTranslatedNote({
        type: "clause",
        clauseKey: currentNode.key,
        sourceText: currentNode.sourceText,
        clauseLabel: getLabelForKey(currentNode.key),
        targetLanguage: "ko",
      });
      completedRequests += Number(currentNode.requestCount || 0);
      state.ui.translationJob = {
        ...state.ui.translationJob,
        completedRequests,
        currentLabel: getLabelForKey(currentNode.key),
      };
      renderTranslationStatus();
    }
    setMessage(`절 번역 완료: ${translationNodes.length}개 절`, false);
  } finally {
    window.setTimeout(() => {
      state.ui.translationJob = null;
      renderTranslationStatus();
    }, TRANSIENT_STATUS_HIDE_DELAY_MS);
    endBusy();
  }
}

function collectTranslationNodes(node) {
  if (!node) {
    return [];
  }
  const hasExistingClauseNote = getNotesForClause(node.key).some((note) => note.type === "clause");
  const sourceText = getClauseSourceText(node);
  const current = sourceText && !hasExistingClauseNote ? [{ key: node.key, sourceText, requestCount: estimateTranslationRequestCount(sourceText) }] : [];
  return [...current, ...(node.children || []).flatMap((child) => collectTranslationNodes(child))];
}

function estimateTranslationRequestCount(text) {
  return splitTranslationText(text).length;
}

function splitTranslationText(text, limit = TRANSLATION_CHUNK_LIMIT) {
  const cleaned = String(text || "").trim();
  if (!cleaned) {
    return [];
  }
  if (cleaned.length <= limit) {
    return [cleaned];
  }

  const paragraphs = cleaned
    .split(/\n{2,}/)
    .map((part) => part.trim())
    .filter(Boolean);
  const units = paragraphs.length ? paragraphs : [cleaned];
  const chunks = [];
  let currentParts = [];
  let currentLength = 0;

  units.forEach((paragraph) => {
    if (paragraph.length > limit) {
      if (currentParts.length) {
        chunks.push(currentParts.join("\n\n"));
        currentParts = [];
        currentLength = 0;
      }
      chunks.push(paragraph);
      return;
    }

    const separator = currentParts.length ? 2 : 0;
    const nextLength = currentLength + separator + paragraph.length;
    if (currentParts.length && nextLength > limit) {
      chunks.push(currentParts.join("\n\n"));
      currentParts = [paragraph];
      currentLength = paragraph.length;
      return;
    }

    currentParts.push(paragraph);
    currentLength = nextLength;
  });

  if (currentParts.length) {
    chunks.push(currentParts.join("\n\n"));
  }

  return chunks.filter(Boolean);
}

function getClauseSourceText(node) {
  if (!node) {
    return "";
  }
  const text = String(node.text || "").trim();
  if (text) {
    return text;
  }
  const blockText = (node.blocks || [])
    .flatMap((block) => {
      if (block.type === "paragraph") {
        return [String(block.text || "").trim()];
      }
      if (block.type === "table") {
        return (block.cells || []).flat().map((cell) => String(cell.text || "").trim());
      }
      if (block.type === "image") {
        return [String(block.alt || "").trim()];
      }
      return [];
    })
    .filter(Boolean)
    .join("\n");
  return blockText || String(node.clauseTitle || "").trim();
}

async function createTranslatedNote({ type, clauseKey, blockIndex = -1, rowIndex = -1, cellIndex = -1, cellId = "", rowText = "", sourceText, clauseLabel, targetLanguage }) {
  try {
    const sourceLanguage = inferSourceLanguage(sourceText);
    state.ui.translationTask = {
      status: "queued",
      queuedPosition: 0,
      label: type === "clause" ? "절 메모 번역" : "선택 메모 번역",
    };
    renderTranslationStatus();
    const response = await streamLlmAction("/api/clause-browser/llm-actions", {
      actionType: "translate",
      text: sourceText,
      sourceLanguage,
      targetLanguage,
      context: clauseLabel,
    });
    upsertNote({
      id: type === "clause" ? `${clauseKey}:clause` : `selection:${Date.now()}:${Math.random().toString(36).slice(2, 8)}`,
      type,
      clauseKey,
      blockId: getBlockIdByIndex(clauseKey, blockIndex),
      blockIndex,
      rowIndex,
      cellIndex,
      cellId,
      rowText,
      clauseLabel,
      sourceText,
      translation: response.outputText || response.data?.outputText || "",
      sourceLanguage,
      targetLanguage,
      collapsed: false,
    });
    if (!state.ui.translationJob || Number(state.ui.translationJob.totalRequests || 0) <= 1) {
      setMessage(`번역 완료: ${type === "clause" ? "절 메모" : "선택 메모"}`, false);
    }
  } catch (error) {
    if (!isAbortedRequestError(error)) {
      setMessage(error.message, true);
    }
  } finally {
    state.ui.translationTask = null;
    renderTranslationStatus();
  }
}

function getNotesForClause(clauseKey) {
  return (state.ui.notes || []).filter((note) => note.clauseKey === clauseKey);
}

function getSelectionNotesForTarget(clauseKey, blockIndex, rowIndex = -1, cellIndex = null, blockId = getBlockIdByIndex(clauseKey, blockIndex), cellId = "") {
  return (state.ui.notes || []).filter(
    (note) =>
      note.type === "selection" &&
      blockReferenceMatches(note, clauseKey, blockIndex, blockId) &&
      Number(note.rowIndex ?? -1) === Number(rowIndex) &&
      (cellId
        ? String(note.cellId || "") === String(cellId)
        : cellIndex === null || Number(note.cellIndex ?? -1) === Number(cellIndex))
  );
}

function upsertNote(note) {
  const existingIndex = (state.ui.notes || []).findIndex((item) => item.id === note.id);
  if (existingIndex >= 0) {
    state.ui.notes = state.ui.notes.map((item, index) => (index === existingIndex ? { ...item, ...note } : item));
  } else {
    state.ui.notes = [note, ...(state.ui.notes || [])];
  }
  if (note.type === "selection") {
    ensureHighlightEntry(
      createHighlightEntry({
        clauseKey: note.clauseKey,
        blockId: note.blockId,
        blockIndex: note.blockIndex,
        rowIndex: note.rowIndex,
        cellIndex: note.cellIndex,
        cellId: note.cellId,
        rowText: note.rowText,
      })
    );
  }
  if (note.type === "clause" && note.clauseKey) {
    expandNodePath(note.clauseKey);
  }
  persistSessionState();
  renderLoadedTree();
}

function expandNodePath(targetKey) {
  const keys = new Set(state.ui.expandedKeys || []);

  function visit(node, ancestors = []) {
    if (!node) {
      return false;
    }
    if (node.key === targetKey) {
      ancestors.forEach((key) => keys.add(key));
      keys.add(node.key);
      return true;
    }
    return (node.children || []).some((child) => visit(child, [...ancestors, node.key]));
  }

  (state.loadedRoots || []).some((root) => visit(root, []));
  state.ui.expandedKeys = keys;
}

function updateNoteField(noteId, field, value) {
  state.ui.notes = (state.ui.notes || []).map((note) => (note.id === noteId ? { ...note, [field]: value } : note));
  persistSessionState();
}

function toggleClauseNotes(clauseKey) {
  if (state.ui.clauseNoteModalKey === clauseKey) {
    closeClauseNoteModal();
  } else {
    openClauseNoteModal(clauseKey);
  }
  renderLoadedTree();
}

function toggleSelectionNotes(clauseKey, blockIndex, rowIndex = -1, cellIndex = null, blockId = getBlockIdByIndex(clauseKey, blockIndex), cellId = "") {
  const notes = getSelectionNotesForTarget(clauseKey, blockIndex, rowIndex, cellIndex, blockId, cellId);
  if (!notes.length) {
    return;
  }
  const shouldCollapse = notes.some((note) => !note.collapsed);
  const ids = new Set(notes.map((note) => note.id));
  state.ui.notes = (state.ui.notes || []).map((note) =>
    ids.has(note.id) ? { ...note, collapsed: shouldCollapse } : note
  );
  persistSessionState();
  renderLoadedTree();
}

function deleteNote(noteId) {
  const targetNote = (state.ui.notes || []).find((note) => note.id === noteId) || null;
  state.ui.notes = (state.ui.notes || []).filter((note) => note.id !== noteId);
  if (targetNote?.type === "selection") {
    pruneHighlightForSelectionNote(targetNote);
  }
  if (state.ui.clauseNoteModalKey) {
    const remaining = getNotesForClause(state.ui.clauseNoteModalKey).filter((note) => note.type === "clause" && note.id !== noteId);
    if (!remaining.length) {
      state.ui.clauseNoteModalKey = "";
      elements.clauseNoteModal.classList.add("hidden");
      elements.clauseNoteModal.setAttribute("aria-hidden", "true");
    }
  }
  persistSessionState();
  renderLoadedTree();
  if (state.ui.clauseNoteModalKey) {
    renderClauseNoteModal();
  }
}

function pruneHighlightForSelectionNote(note) {
  const linkedEntry = createHighlightEntry({
    clauseKey: note.clauseKey,
    blockId: note.blockId,
    blockIndex: note.blockIndex,
    rowIndex: note.rowIndex,
    cellIndex: note.cellIndex,
    cellId: note.cellId,
    rowText: note.rowText,
  });
  if (!linkedEntry) {
    return;
  }
  const hasSiblingSelectionNote = (state.ui.notes || []).some(
    (item) =>
      item.type === "selection" &&
      item.id !== note.id &&
      item.clauseKey === note.clauseKey &&
      String(item.blockId || "") === String(note.blockId || "") &&
      Number(item.blockIndex ?? -1) === Number(note.blockIndex ?? -1) &&
      Number(item.rowIndex ?? -1) === Number(note.rowIndex ?? -1) &&
      Number(item.cellIndex ?? -1) === Number(note.cellIndex ?? -1) &&
      String(item.cellId || "") === String(note.cellId || "")
  );
  if (hasSiblingSelectionNote) {
    return;
  }
  state.ui.highlights = (state.ui.highlights || []).filter((item) => item.id !== linkedEntry.id);
}

function pruneNotesForNodeKey(nodeKey) {
  const node = findNodeByKey(nodeKey);
  if (!node) {
    return;
  }
  const subtreeKeys = new Set(collectNodeKeys(node));
  state.ui.notes = (state.ui.notes || []).filter((note) => !subtreeKeys.has(note.clauseKey));
}

function pruneHighlightsForNodeKey(nodeKey) {
  const node = findNodeByKey(nodeKey);
  if (!node) {
    return;
  }
  const subtreeKeys = new Set(collectNodeKeys(node));
  state.ui.highlights = (state.ui.highlights || []).filter((item) => !subtreeKeys.has(item.clauseKey));
}

function collectNodeKeys(node) {
  return [node.key, ...(node.children || []).flatMap((child) => collectNodeKeys(child))];
}

function inferSourceLanguage(text) {
  return /[ㄱ-ㅎㅏ-ㅣ가-힣]/.test(String(text || "")) ? "ko" : "en";
}

function inferTargetLanguage(text) {
  return inferSourceLanguage(text) === "ko" ? "en" : "ko";
}

function getCurrentSelectionHighlightEntry() {
  const clauseKey = String(state.ui.selection?.clauseKey || "").trim();
  const blockId = String(state.ui.selection?.blockId || "").trim();
  const blockIndex = Number(state.ui.selection?.blockIndex ?? -1);
  const rowIndex = Number(state.ui.selection?.rowIndex ?? -1);
  const cellIndex = Number(state.ui.selection?.cellIndex ?? -1);
  const cellId = String(state.ui.selection?.cellId || "").trim();
  const rowText = String(state.ui.selection?.rowText || "").trim();
  if (!clauseKey || blockIndex < 0) {
    return null;
  }
  return createHighlightEntry({ clauseKey, blockId, blockIndex, rowIndex, cellIndex, cellId, rowText });
}

function createHighlightEntry({ clauseKey, blockId = "", blockIndex = -1, rowIndex = -1, cellIndex = -1, cellId = "", rowText = "" }) {
  const normalizedClauseKey = String(clauseKey || "").trim();
  const normalizedBlockId = String(blockId || "").trim();
  const normalizedBlockIndex = Number(blockIndex ?? -1);
  if (!normalizedClauseKey || (!normalizedBlockId && normalizedBlockIndex < 0)) {
    return null;
  }
  const normalizedRowIndex = Number(rowIndex ?? -1);
  const normalizedCellIndex = Number(cellIndex ?? -1);
  const normalizedCellId = String(cellId || "").trim();
  const normalizedRowText = String(rowText || "").trim();
  return {
    id: `manual:${normalizedClauseKey}:${normalizedBlockId || normalizedBlockIndex}:${normalizedCellId || `${normalizedRowIndex}:${normalizedCellIndex}`}:${normalizeHighlightText(normalizedRowText) || "block"}`,
    type: "manual",
    clauseKey: normalizedClauseKey,
    blockId: normalizedBlockId,
    blockIndex: normalizedBlockIndex,
    rowIndex: normalizedRowIndex,
    cellIndex: normalizedCellIndex,
    cellId: normalizedCellId,
    rowText: normalizedRowText,
  };
}

function ensureHighlightEntry(entry) {
  if (!entry) {
    return;
  }
  const exists = (state.ui.highlights || []).some((item) => item.id === entry.id);
  if (!exists) {
    state.ui.highlights = [entry, ...(state.ui.highlights || [])];
  }
}

function toggleSelectionHighlight() {
  const entry = getCurrentSelectionHighlightEntry();
  if (!entry) {
    setMessage("Highlight할 문단이나 표 행을 먼저 선택하세요.", true);
    return;
  }
  const exists = (state.ui.highlights || []).some((item) => item.id === entry.id);
  state.ui.highlights = exists
    ? (state.ui.highlights || []).filter((item) => item.id !== entry.id)
    : [entry, ...(state.ui.highlights || [])];
  persistSessionState();
  renderLoadedTree();
}

function addManualSelectionNote() {
  const clauseKey = String(state.ui.selection?.clauseKey || "").trim();
  const blockId = String(state.ui.selection?.blockId || "").trim();
  const blockIndex = Number(state.ui.selection?.blockIndex ?? -1);
  const rowIndex = Number(state.ui.selection?.rowIndex ?? -1);
  const cellIndex = Number(state.ui.selection?.cellIndex ?? -1);
  const cellId = String(state.ui.selection?.cellId || "").trim();
  if (!clauseKey || blockIndex < 0) {
    setMessage("메모를 추가할 문단이나 표 셀을 먼저 선택하세요.", true);
    return;
  }
  const sourceText = String(
    state.ui.selection?.hasSelection && state.ui.selection?.text
      ? state.ui.selection.text
      : state.ui.selection?.rowText || ""
  ).trim();
  upsertNote({
    id: `manual-note:${Date.now()}:${Math.random().toString(36).slice(2, 8)}`,
    type: "selection",
    clauseKey,
    blockId,
    blockIndex,
    rowIndex,
    cellIndex,
    cellId,
    rowText: String(state.ui.selection?.rowText || ""),
    clauseLabel: String(state.ui.selection?.clauseLabel || ""),
    sourceText,
    translation: "",
    sourceLanguage: inferSourceLanguage(sourceText),
    targetLanguage: "memo",
    collapsed: false,
  });
}

function renderSpecbotResults() {
  if (!state.ui.specbotResults.length) {
    elements.specbotResultList.innerHTML = '<div class="muted">상단 Query로 SpecBot을 실행하면 결과가 여기에 표시됩니다.</div>';
    return;
  }
  elements.specbotResultList.innerHTML = state.ui.specbotResults
    .map(
      (item) => `
        <article class="result-card">
          <strong>${escapeHtml(item.specNo)} / ${escapeHtml(item.clauseId)}</strong>
          <div class="muted">${escapeHtml((item.clausePath || []).join(" > "))}</div>
          <div class="muted">${escapeHtml(item.textPreview || "")}</div>
          <div class="tree-actions">
            <button
              class="success icon-button"
              type="button"
              title="이 절 추가"
              aria-label="이 절 추가"
              data-action="load-specbot-hit"
              data-spec-no="${escapeHtml(item.specNo)}"
              data-clause-id="${escapeHtml(item.clauseId)}"
            >O</button>
            <button
              class="danger icon-button"
              type="button"
              title="거절"
              aria-label="거절"
              data-action="reject-specbot-hit"
              data-spec-no="${escapeHtml(item.specNo)}"
              data-clause-id="${escapeHtml(item.clauseId)}"
            >✕</button>
          </div>
        </article>
      `
    )
    .join("");
  elements.specbotResultList.querySelectorAll("[data-action='load-specbot-hit']").forEach((button) => {
    button.addEventListener("click", async () => {
      const hit = state.ui.specbotResults.find(
        (item) => String(item.specNo || "") === String(button.dataset.specNo || "")
          && String(item.clauseId || "") === String(button.dataset.clauseId || "")
      );
      await loadClauseFromSpec(button.dataset.specNo, button.dataset.clauseId);
      if (hit) {
        persistSessionState();
        renderLoadedTree();
      }
      removeSpecbotResult(button.dataset.specNo, button.dataset.clauseId);
    });
  });
  elements.specbotResultList.querySelectorAll("[data-action='reject-specbot-hit']").forEach((button) => {
    button.addEventListener("click", () => {
      addRejectedSpecbotClause(button.dataset.specNo, button.dataset.clauseId);
      removeSpecbotResult(button.dataset.specNo, button.dataset.clauseId);
      setMessage(
        `SpecBot 결과에서 ${button.dataset.specNo} / ${button.dataset.clauseId} 절을 거절하고 이후 검색에서도 제외합니다.`,
        false
      );
    });
  });
}

function showNodeMenu(x, y, key) {
  state.ui.nodeMenu = { key, x, y };
  elements.nodeMenu.style.left = `${x}px`;
  elements.nodeMenu.style.top = `${y}px`;
  elements.nodeMenu.classList.remove("hidden");
}

function hideNodeMenu() {
  state.ui.nodeMenu = { key: "", x: 0, y: 0 };
  elements.nodeMenu.classList.add("hidden");
}

async function runSpecbotQuery() {
  if (!beginBusy(SPECBOT_QUERY_BUSY_LABEL)) {
    return;
  }
  const query = elements.specbotQuery.value.trim();
  state.ui.specbotQueryText = query;
  persistSessionState();
  if (!query) {
    endBusy();
    setMessage("SpecBot query를 입력하세요.", true);
    return;
  }
  state.ui.specbotQueryStatus = "queued";
  setSpecbotQueryLoading(true);
  try {
    const exclusions = buildSpecbotExclusions();
    const queryDepth = getSelectedSpecbotDepth();
    state.ui.specbotResults = [];
    state.ui.specbotSettings = {
      ...state.ui.specbotSettings,
      iterations: getIterationsForDepth(queryDepth),
      queryDepth,
    };
    persistSessionState();
    renderSpecbotResults();
    const response = await streamSpecbotQuery({
      query,
      releaseData: getBoardScope().releaseData,
      release: getBoardScope().release,
      settings: {
        ...state.ui.specbotSettings,
        iterations: getIterationsForDepth(queryDepth),
        queryDepth,
      },
      excludeSpecs: exclusions.excludeSpecs,
      excludeClauses: exclusions.excludeClauses,
    });
    state.ui.specbotResults = filterSpecbotHitsByExclusions(response.hits || [], exclusions).sort(compareSpecbotHits);
    persistSessionState();
    renderSpecbotResults();
    setMessage(`SpecBot query 완료: ${query}`, false);
  } catch (error) {
    if (!isAbortedRequestError(error)) {
      setMessage(error.message, true);
    }
  } finally {
    state.ui.specbotQueryStatus = "";
    setSpecbotQueryLoading(false);
    endBusy();
  }
}

function buildSpecbotExclusions() {
  const settings = state.ui.specbotSettings || {};
  const includedSpecs = new Set(
    Array.isArray(settings.includedSpecs) && settings.includedSpecs.length
      ? settings.includedSpecs.map((item) => String(item).trim()).filter(Boolean)
      : (state.documents || []).map((item) => String(item.specNo || "").trim()).filter(Boolean)
  );
  const excludeSpecs = new Set(Array.isArray(settings.excludeSpecs) ? settings.excludeSpecs.map((item) => String(item).trim()).filter(Boolean) : []);
  (state.documents || []).forEach((item) => {
    const specNo = String(item.specNo || "").trim();
    if (specNo && !includedSpecs.has(specNo)) {
      excludeSpecs.add(specNo);
    }
  });
  const excludeClauseMap = new Map();

  const manualClauses = Array.isArray(settings.excludeClauses) ? settings.excludeClauses : [];
  manualClauses.forEach((item) => {
    const specNo = String(item.specNo || "").trim();
    const clauseId = String(item.clauseId || "").trim();
    if (specNo && clauseId) {
      excludeClauseMap.set(`${specNo}:${clauseId}`, { specNo, clauseId });
    }
  });

  getRejectedSpecbotClauses().forEach((item) => {
    excludeClauseMap.set(`${item.specNo}:${item.clauseId}`, item);
  });

  collectLoadedClausePairs(state.loadedRoots).forEach((item) => {
    excludeClauseMap.set(`${item.specNo}:${item.clauseId}`, item);
  });

  return {
    excludeSpecs: [...excludeSpecs].sort(compareMixedToken),
    excludeClauses: [...excludeClauseMap.values()].sort((left, right) => compareSpecbotHits(left, right)),
  };
}

function filterSpecbotHitsByExclusions(hits, exclusions = buildSpecbotExclusions()) {
  const excludeSpecs = new Set((exclusions.excludeSpecs || []).map((item) => String(item || "").trim()).filter(Boolean));
  const excludeClausePairs = new Set(
    (exclusions.excludeClauses || [])
      .map((item) => {
        const specNo = String(item.specNo || "").trim();
        const clauseId = String(item.clauseId || "").trim();
        return specNo && clauseId ? `${specNo}:${clauseId}` : "";
      })
      .filter(Boolean)
  );
  return (hits || []).filter((item) => {
    const specNo = String(item.specNo || "").trim();
    const clauseId = String(item.clauseId || "").trim();
    if (!specNo || !clauseId) {
      return false;
    }
    if (excludeSpecs.has(specNo)) {
      return false;
    }
    if (excludeClausePairs.has(`${specNo}:${clauseId}`)) {
      return false;
    }
    return true;
  });
}

function pruneSpecbotResultsByCurrentExclusions() {
  state.ui.specbotResults = filterSpecbotHitsByExclusions(state.ui.specbotResults, buildSpecbotExclusions()).sort(compareSpecbotHits);
}

function collectLoadedClausePairs(nodes) {
  return (nodes || []).flatMap((node) => [
    { specNo: String(node.specNo || "").trim(), clauseId: String(node.clauseId || "").trim() },
    ...collectLoadedClausePairs(node.children || []),
  ]).filter((item) => item.specNo && item.clauseId);
}

function parseSpecbotExcludeSpecs(text) {
  return String(text || "")
    .split(/\r?\n|,/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function parseSpecbotExcludeClauses(text) {
  return String(text || "")
    .split(/\r?\n|,/)
    .map((item) => item.trim())
    .filter(Boolean)
    .map((item) => {
      const [specNo, clauseId] = item.split(":");
      return { specNo: String(specNo || "").trim(), clauseId: String(clauseId || "").trim() };
    })
    .filter((item) => item.specNo && item.clauseId);
}

function dedupeClausePairs(items) {
  const pairs = new Map();
  (items || []).forEach((item) => {
    const specNo = String(item.specNo || "").trim();
    const clauseId = String(item.clauseId || "").trim();
    if (specNo && clauseId) {
      pairs.set(`${specNo}:${clauseId}`, { specNo, clauseId });
    }
  });
  return [...pairs.values()];
}

function getNormalizedRejectedClauses(items) {
  return dedupeClausePairs(Array.isArray(items) ? items : []);
}

function getRejectedSpecbotClauses() {
  return getNormalizedRejectedClauses(state.ui.specbotSettings?.rejectedClauses);
}

function renderSpecbotDocumentSettings() {
  const docs = state.documents || [];
  if (state.ui.specbotDocumentSettingsLoading) {
    elements.settingDocumentList.innerHTML = '<div class="muted">문서 목록을 불러오는 중입니다.</div>';
    elements.settingDocumentSelectionCount.textContent = "0 / 0 selected";
    return;
  }
  if (!docs.length) {
    elements.settingDocumentList.innerHTML = '<div class="muted">선택 가능한 문서가 없습니다.</div>';
    elements.settingDocumentSelectionCount.textContent = "0 / 0 selected";
    return;
  }
  const selectedSpecs = new Set(
    Array.isArray(state.ui.specbotSettings?.includedSpecs) && state.ui.specbotSettings.includedSpecs.length
      ? state.ui.specbotSettings.includedSpecs.map((item) => String(item).trim()).filter(Boolean)
      : docs.map((item) => String(item.specNo || "").trim()).filter(Boolean)
  );
  elements.settingDocumentList.innerHTML = docs
    .map(
      (item) => `
        <label class="settings-document-row">
          <input type="checkbox" data-action="toggle-specbot-doc" value="${escapeHtml(item.specNo)}" ${selectedSpecs.has(item.specNo) ? "checked" : ""} />
          <span class="settings-document-text">
            <strong>${escapeHtml(item.specNo)}</strong>
            <span class="muted">${escapeHtml(item.specTitle || "")}</span>
          </span>
        </label>
      `
    )
    .join("");
  elements.settingDocumentList.querySelectorAll("[data-action='toggle-specbot-doc']").forEach((input) => {
    input.addEventListener("change", updateSpecbotDocumentSelectionCount);
  });
  updateSpecbotDocumentSelectionCount();
}

function renderRejectedSpecbotClauses() {
  const rejectedClauses = getRejectedSpecbotClauses();
  if (!rejectedClauses.length) {
    elements.settingRejectedClauseList.innerHTML = '<div class="muted">거절로 제외된 절이 없습니다.</div>';
    elements.settingClearRejectedClauses.disabled = true;
    return;
  }

  elements.settingClearRejectedClauses.disabled = false;
  elements.settingRejectedClauseList.innerHTML = rejectedClauses
    .sort(compareSpecbotHits)
    .map(
      (item) => `
        <div class="settings-rejected-row">
          <div class="settings-rejected-text">
            <strong>${escapeHtml(item.specNo)}</strong>
            <span>${escapeHtml(item.clauseId)}</span>
          </div>
          <button
            class="ghost"
            type="button"
            data-action="remove-rejected-clause"
            data-spec-no="${escapeHtml(item.specNo)}"
            data-clause-id="${escapeHtml(item.clauseId)}"
          >
            해제
          </button>
        </div>
      `
    )
    .join("");

  elements.settingRejectedClauseList.querySelectorAll("[data-action='remove-rejected-clause']").forEach((button) => {
    button.addEventListener("click", () => {
      removeRejectedSpecbotClause(button.dataset.specNo, button.dataset.clauseId);
    });
  });
}

function getSelectedSpecbotDocuments() {
  return [...elements.settingDocumentList.querySelectorAll("[data-action='toggle-specbot-doc']:checked")]
    .map((input) => String(input.value || "").trim())
    .filter(Boolean);
}

function updateSpecbotDocumentSelectionCount() {
  const selectedCount = getSelectedSpecbotDocuments().length;
  const totalCount = (state.documents || []).length;
  elements.settingDocumentSelectionCount.textContent = `${selectedCount} / ${totalCount} selected`;
}

function setAllSpecbotDocuments(checked) {
  elements.settingDocumentList.querySelectorAll("[data-action='toggle-specbot-doc']").forEach((input) => {
    input.checked = checked;
  });
  updateSpecbotDocumentSelectionCount();
}

function setSpecbotQueryLoading(isLoading) {
  const queryStatus = String(state.ui.specbotQueryStatus || "").trim();
  const label = !isLoading ? "" : queryStatus === "queued" ? "대기 중" : queryStatus === "started" ? "실행 중" : "수행 중";
  elements.specbotQuery.disabled = isLoading;
  elements.specbotSpinner.classList.toggle("hidden", !isLoading);
  elements.runSpecbotLabel.textContent = label;
  elements.specbotQueryStatus.classList.toggle("hidden", !isLoading);
}

function getIterationsForDepth(depth) {
  if (depth === "short") {
    return 0;
  }
  if (depth === "long") {
    return 2;
  }
  return 1;
}

function getSpecbotDepthFromSettings(settings = {}) {
  if (settings.queryDepth === "short" || settings.queryDepth === "medium" || settings.queryDepth === "long") {
    return settings.queryDepth;
  }
  const iterations = Number(settings.iterations);
  if (iterations <= 0) {
    return "short";
  }
  if (iterations >= 2) {
    return "long";
  }
  return "medium";
}

function applySpecbotDepthSelection(depth) {
  const normalizedDepth = depth === "short" || depth === "long" ? depth : "medium";
  (elements.specbotDepthOptions || []).forEach((input) => {
    input.checked = input.value === normalizedDepth;
  });
}

function getSelectedSpecbotDepth() {
  const selected = (elements.specbotDepthOptions || []).find((input) => input.checked);
  return selected?.value === "short" || selected?.value === "long" ? selected.value : "medium";
}

function addRejectedSpecbotClause(specNo, clauseId) {
  state.ui.specbotSettings = {
    ...state.ui.specbotSettings,
    rejectedClauses: dedupeClausePairs([...getRejectedSpecbotClauses(), { specNo, clauseId }]),
  };
  persistSessionState();
  if (state.ui.isSpecbotSettingsOpen) {
    renderRejectedSpecbotClauses();
  }
}

function removeRejectedSpecbotClause(specNo, clauseId) {
  state.ui.specbotSettings = {
    ...state.ui.specbotSettings,
    rejectedClauses: getRejectedSpecbotClauses().filter(
      (item) => !(item.specNo === specNo && item.clauseId === clauseId)
    ),
  };
  persistSessionState();
  renderRejectedSpecbotClauses();
  setMessage(`거절 제외를 해제했습니다: ${specNo} / ${clauseId}`, false);
}

function clearRejectedSpecbotClauses() {
  state.ui.specbotSettings = {
    ...state.ui.specbotSettings,
    rejectedClauses: [],
  };
  persistSessionState();
  renderRejectedSpecbotClauses();
  setMessage("거절하여 제외한 절을 모두 해제했습니다.", false);
}

function removeSpecbotResult(specNo, clauseId) {
  state.ui.specbotResults = state.ui.specbotResults.filter(
    (item) => !(item.specNo === specNo && item.clauseId === clauseId)
  );
  persistSessionState();
  renderSpecbotResults();
}

function clearSpecbotResults() {
  state.ui.specbotResults = [];
  persistSessionState();
  renderSpecbotResults();
  setMessage("SpecBot 결과를 비웠습니다.", false);
}

async function exportDocx() {
  if (!beginBusy("DOCX 저장 중입니다.")) {
    return;
  }
  if (!state.loadedRoots.length) {
    endBusy();
    setMessage("저장할 절이 없습니다.", true);
    return;
  }
  const boardTitle = document.getElementById("board-post-title")?.value?.trim() || "";
  const exportInputTitle = elements.exportTitle?.value?.trim?.() || "";
  const title = boardTitle || exportInputTitle;
  if (!title) {
    endBusy();
    setMessage("게시글 제목이 없습니다.", true);
    return;
  }

  try {
    const response = await fetch("/api/clause-browser/exports/docx/download", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      },
      body: JSON.stringify({
        title,
        roots: state.loadedRoots,
        notes: state.ui.notes || [],
        highlights: state.ui.highlights || [],
      }),
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      const detail = payload?.detail || "DOCX export failed";
      throw new Error(formatErrorMessage(detail));
    }
    const blob = await response.blob();
    const downloadUrl = window.URL.createObjectURL(blob);
    const disposition = response.headers.get("Content-Disposition") || "";
    const utf8Match = disposition.match(/filename\*=UTF-8''([^;]+)/i);
    const asciiMatch = disposition.match(/filename="([^"]+)"/i);
    const fileName = utf8Match?.[1]
      ? decodeURIComponent(utf8Match[1])
      : (asciiMatch?.[1] || `${title}.docx`);
    const anchor = document.createElement("a");
    anchor.href = downloadUrl;
    anchor.download = fileName;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    window.URL.revokeObjectURL(downloadUrl);
    setMessage(`Export 완료: ${fileName}`, false);
  } catch (error) {
    if (!isAbortedRequestError(error)) {
      setMessage(error.message, true);
    }
  } finally {
    endBusy();
  }
}

function beginBusy(label, options = {}) {
  if (options.guard === false) {
    return true;
  }
  if (options.allowDuringSpecbotQuery && state.ui.busy === SPECBOT_QUERY_BUSY_LABEL) {
    return true;
  }
  if (state.ui.busy) {
    if (!options.silent) {
      setMessage(`다른 작업이 진행 중입니다: ${state.ui.busy}`, true);
    }
    return false;
  }
  state.ui.busy = label;
  updateBusyUi();
  return true;
}

function endBusy(options = {}) {
  if (options.guard === false) {
    return;
  }
  if (options.allowDuringSpecbotQuery && state.ui.busy === SPECBOT_QUERY_BUSY_LABEL) {
    return;
  }
  state.ui.busy = null;
  updateBusyUi();
}

function updateBusyUi() {
  const isBusy = Boolean(state.ui.busy);
  const allowsDocumentBrowsing = [
    SPECBOT_QUERY_BUSY_LABEL,
    DOCUMENT_SEARCH_BUSY_LABEL,
    DOCUMENT_SELECT_BUSY_LABEL,
  ].includes(state.ui.busy);
  elements.openPickerButton.disabled = isBusy && !allowsDocumentBrowsing;
  elements.documentSearch.disabled = isBusy && !allowsDocumentBrowsing;
  elements.clauseSearch.disabled = isBusy && !allowsDocumentBrowsing;
  if (elements.exportButton) {
    elements.exportButton.disabled = isBusy;
  }
  elements.openSpecbotSettings.disabled = isBusy;
  elements.specbotQuery.disabled = isBusy;
}

function setMessage(text, isError) {
  const message = formatErrorMessage(text);
  state.ui.message = { text: message, isError };
  if (messageHideTimer) {
    window.clearTimeout(messageHideTimer);
    messageHideTimer = 0;
  }
  elements.messageBar.innerHTML = message ? `<div class="message ${isError ? "error" : ""}">${escapeHtml(message)}</div>` : "";
  elements.messageBar.classList.toggle("has-message", Boolean(message));
  if (message && !isError) {
    messageHideTimer = window.setTimeout(() => {
      if (state.ui.message?.text === message && !state.ui.message?.isError) {
        clearMessage();
      }
    }, TRANSIENT_STATUS_HIDE_DELAY_MS);
  }
}

function clearMessage() {
  state.ui.message = null;
  if (messageHideTimer) {
    window.clearTimeout(messageHideTimer);
    messageHideTimer = 0;
  }
  if (elements.messageBar) {
    elements.messageBar.innerHTML = "";
    elements.messageBar.classList.remove("has-message");
  }
}

async function apiGet(url) {
  const { signal, release } = registerRequestController();
  let response;
  try {
    response = await fetch(url, { signal });
  } catch (error) {
    release();
    throw normalizeRequestError(error);
  }
  const payload = await parseResponse(response);
  release();
  if (!response.ok) {
    throw new Error(formatErrorMessage(payload.detail || payload || "Request failed"));
  }
  return payload;
}

async function apiPost(url, body) {
  const { signal, release } = registerRequestController();
  let response;
  try {
    response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal,
    });
  } catch (error) {
    release();
    throw normalizeRequestError(error);
  }
  const payload = await parseResponse(response);
  release();
  if (!response.ok) {
    throw new Error(formatErrorMessage(payload.detail || payload || "Request failed"));
  }
  return payload;
}

async function apiPostWork(url, body) {
  const targetUrl = resolveWorkApiUrl(url);
  const slotId = await reserveLocalWorkSlot();
  activeLocalWorkSlots.add(slotId);
  try {
    const payload = await apiPost(targetUrl, body);
    if (payload && Object.prototype.hasOwnProperty.call(payload, "success")) {
      return payload;
    }
    return { success: true, data: payload };
  } finally {
    activeLocalWorkSlots.delete(slotId);
    await releaseLocalWorkSlot(slotId);
  }
}

async function streamSpecbotQuery(body) {
  const targetUrl = resolveWorkApiUrl("/api/clause-browser/specbot/query").replace(/\/query$/, "/query-stream");
  const slotId = await reserveLocalWorkSlot();
  activeLocalWorkSlots.add(slotId);
  const { signal, release } = registerRequestController();
  let response;
  try {
    response = await fetch(targetUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal,
    });
  } catch (error) {
    release();
    activeLocalWorkSlots.delete(slotId);
    await releaseLocalWorkSlot(slotId);
    throw normalizeRequestError(error);
  }
  if (!response.ok) {
    const payload = await parseResponse(response);
    release();
    activeLocalWorkSlots.delete(slotId);
    await releaseLocalWorkSlot(slotId);
    throw new Error(formatErrorMessage(payload.detail || payload || "Request failed"));
  }

  const reader = response.body?.getReader();
  if (!reader) {
    release();
    throw new Error("SpecBot query stream is unavailable.");
  }

  const decoder = new TextDecoder();
  let buffer = "";
  let finalPayload = { hits: [] };
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) {
        break;
      }
      buffer += decoder.decode(value, { stream: true });
      let lineBreak = buffer.indexOf("\n");
      while (lineBreak >= 0) {
        const line = buffer.slice(0, lineBreak).trim();
        buffer = buffer.slice(lineBreak + 1);
        if (line) {
          const event = JSON.parse(line);
          finalPayload = applySpecbotStreamEvent(event, finalPayload);
        }
        lineBreak = buffer.indexOf("\n");
      }
    }
    const trailing = buffer.trim();
    if (trailing) {
      finalPayload = applySpecbotStreamEvent(JSON.parse(trailing), finalPayload);
    }
  } catch (error) {
    throw normalizeRequestError(error);
  } finally {
    release();
    activeLocalWorkSlots.delete(slotId);
    await releaseLocalWorkSlot(slotId);
  }
  return finalPayload;
}

async function streamLlmAction(url, body) {
  const slotId = await reserveLocalWorkSlot();
  activeLocalWorkSlots.add(slotId);
  const { signal, release } = registerRequestController();
  const response = await fetch(resolveWorkApiUrl(`${url}-stream`), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  }).catch((error) => {
    release();
    activeLocalWorkSlots.delete(slotId);
    releaseLocalWorkSlot(slotId);
    throw normalizeRequestError(error);
  });
  if (!response.ok) {
    const payload = await parseResponse(response);
    release();
    activeLocalWorkSlots.delete(slotId);
    await releaseLocalWorkSlot(slotId);
    throw new Error(formatErrorMessage(payload.detail || payload || "Request failed"));
  }
  const reader = response.body?.getReader();
  if (!reader) {
    release();
    activeLocalWorkSlots.delete(slotId);
    await releaseLocalWorkSlot(slotId);
    throw new Error("LLM action stream is unavailable.");
  }

  const decoder = new TextDecoder();
  let buffer = "";
  let finalPayload = {};
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) {
        break;
      }
      buffer += decoder.decode(value, { stream: true });
      let lineBreak = buffer.indexOf("\n");
      while (lineBreak >= 0) {
        const line = buffer.slice(0, lineBreak).trim();
        buffer = buffer.slice(lineBreak + 1);
        if (line) {
          finalPayload = applyLlmActionStreamEvent(JSON.parse(line), finalPayload);
        }
        lineBreak = buffer.indexOf("\n");
      }
    }
    const trailing = buffer.trim();
    if (trailing) {
      finalPayload = applyLlmActionStreamEvent(JSON.parse(trailing), finalPayload);
    }
  } catch (error) {
    throw normalizeRequestError(error);
  } finally {
    release();
    activeLocalWorkSlots.delete(slotId);
    await releaseLocalWorkSlot(slotId);
  }
  return finalPayload;
}

function applySpecbotStreamEvent(event, finalPayload) {
  if (!event || typeof event !== "object") {
    return finalPayload;
  }
  if (event.type === "status") {
    if (event.status === "queued") {
      state.ui.specbotQueryStatus = "queued";
      setSpecbotQueryLoading(true);
      const queuedPosition = Number(event.queuedPosition || 0);
      setMessage(
        queuedPosition > 0
          ? `SpecBot query 대기 중: 대기열 ${queuedPosition}번째`
          : "SpecBot query 대기 중입니다.",
        false
      );
    } else if (event.status === "started") {
      state.ui.specbotQueryStatus = "started";
      setSpecbotQueryLoading(true);
      setMessage("SpecBot query 실행 중입니다.", false);
    }
    return finalPayload;
  }
  if (event.type === "hit") {
    const exclusions = buildSpecbotExclusions();
    state.ui.specbotResults = mergeSpecbotHits(state.ui.specbotResults, [event.hit], exclusions);
    persistSessionState();
    renderSpecbotResults();
    state.ui.specbotQueryStatus = "started";
    setSpecbotQueryLoading(true);
    setMessage(`SpecBot query 진행 중: ${event.hit?.specNo || ""} / ${event.hit?.clauseId || ""}`, false);
    return {
      ...finalPayload,
      hits: mergeSpecbotHits(finalPayload.hits || [], [event.hit], exclusions),
    };
  }
  if (event.type === "hits") {
    const exclusions = buildSpecbotExclusions();
    state.ui.specbotResults = mergeSpecbotHits(state.ui.specbotResults, event.hits || [], exclusions);
    persistSessionState();
    renderSpecbotResults();
    state.ui.specbotQueryStatus = "started";
    setSpecbotQueryLoading(true);
    setMessage(`SpecBot query 진행 중: iteration ${event.iteration}`, false);
    return {
      ...finalPayload,
      hits: mergeSpecbotHits(finalPayload.hits || [], event.hits || [], exclusions),
    };
  }
  if (event.type === "done") {
    return { ...finalPayload, ...event };
  }
  if (event.type === "error") {
    throw new Error(formatErrorMessage(event.detail || `Request failed (${event.status || "error"})`));
  }
  return finalPayload;
}

function applyLlmActionStreamEvent(event, finalPayload) {
  if (!event || typeof event !== "object") {
    return finalPayload;
  }
  if (event.type === "status") {
    state.ui.translationTask = {
      ...(state.ui.translationTask || {}),
      status: String(event.status || ""),
      queuedPosition: Number(event.queuedPosition || 0),
    };
    renderTranslationStatus();
    return finalPayload;
  }
  if (event.type === "done") {
    state.ui.translationTask = {
      ...(state.ui.translationTask || {}),
      status: "done",
      queuedPosition: 0,
    };
    renderTranslationStatus();
    return event.result || finalPayload;
  }
  if (event.type === "error") {
    throw new Error(formatErrorMessage(event.detail || `Request failed (${event.status || "error"})`));
  }
  return finalPayload;
}

function mergeSpecbotHits(existingHits, incomingHits, exclusions = buildSpecbotExclusions()) {
  const merged = new Map(((existingHits || []).map((item) => [`${item.specNo}:${item.clauseId}`, item])));
  for (const hit of filterSpecbotHitsByExclusions(incomingHits || [], exclusions)) {
    const key = `${hit.specNo}:${hit.clauseId}`;
    if (!merged.has(key)) {
      merged.set(key, hit);
    }
  }
  return [...merged.values()].sort(compareSpecbotHits);
}

function resolveWorkApiUrl(url) {
  const baseUrl = String(state.config?.queryApiUrl || "").trim();
  if (!baseUrl) {
    throw new Error("Query API URL is not configured.");
  }
  if (url === "/api/clause-browser/specbot/query") {
    return `${baseUrl}/query`;
  }
  if (url === "/api/clause-browser/llm-actions") {
    return `${baseUrl}/llm-actions`;
  }
  if (url === "/api/clause-browser/llm-actions-stream") {
    return `${baseUrl}/llm-actions-stream`;
  }
  return url;
}

async function parseResponse(response) {
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return await response.json();
  }
  const text = await response.text();
  return { detail: text || `HTTP ${response.status}` };
}

function formatErrorMessage(value) {
  if (typeof value === "string") {
    const trimmed = value.trim();
    if (!trimmed) {
      return "Request failed";
    }
    if (trimmed.startsWith("{") || trimmed.startsWith("[")) {
      try {
        return formatErrorMessage(JSON.parse(trimmed));
      } catch (_error) {
        return trimmed;
      }
    }
    return trimmed;
  }
  if (Array.isArray(value)) {
    return value.map((item) => formatErrorMessage(item)).filter(Boolean).join("; ") || "Request failed";
  }
  if (value && typeof value === "object") {
    if ("detail" in value) {
      return formatErrorMessage(value.detail);
    }
    if ("msg" in value) {
      const location = Array.isArray(value.loc) ? value.loc.join(".") : "";
      const prefix = location ? `${location}: ` : "";
      return `${prefix}${String(value.msg)}`;
    }
    if ("message" in value) {
      return formatErrorMessage(value.message);
    }
    const parts = Object.entries(value)
      .map(([key, item]) => `${key}: ${formatErrorMessage(item)}`)
      .filter((item) => item && !item.endsWith(": "));
    return parts.join("; ") || "Request failed";
  }
  if (value == null) {
    return "Request failed";
  }
  return String(value);
}

function populateSelect(element, items) {
  element.innerHTML = items.map((item) => `<option value="${escapeHtml(item.value)}">${escapeHtml(item.label)}</option>`).join("");
}

function countNodes(nodes) {
  return nodes.reduce((total, node) => total + 1 + countNodes(node.children || []), 0);
}

function escapeKey(value) {
  return value.replace(/[^a-zA-Z0-9_-]/g, "_");
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

function registerRequestController() {
  const controller = new AbortController();
  activeRequestControllers.add(controller);
  return {
    signal: controller.signal,
    release: () => activeRequestControllers.delete(controller),
  };
}

function abortActiveRequests() {
  activeRequestControllers.forEach((controller) => controller.abort());
  activeRequestControllers.clear();
  const slotIds = [...activeLocalWorkSlots];
  activeLocalWorkSlots.clear();
  slotIds.forEach((slotId) => {
    void releaseLocalWorkSlot(slotId);
  });
}

function normalizeRequestError(error) {
  if (error?.name === "AbortError") {
    return new Error("__REQUEST_ABORTED__");
  }
  return error;
}

function isAbortedRequestError(error) {
  return error instanceof Error && error.message === "__REQUEST_ABORTED__";
}

async function reserveLocalWorkSlot() {
  return await withLocalWorkLock(() => {
    const entries = readLocalWorkSlots();
    if (entries.length >= LOCAL_WORK_SLOT_LIMIT) {
      throw new Error("현재 브라우저 작업 대기열이 가득 찼습니다. 잠시 후 다시 시도하세요.");
    }
    const slotId = `${LOCAL_WORK_TAB_ID}:${Date.now()}:${Math.random().toString(36).slice(2, 8)}`;
    entries.push({ id: slotId, tabId: LOCAL_WORK_TAB_ID, createdAt: Date.now() });
    writeLocalWorkSlots(entries);
    return slotId;
  });
}

async function releaseLocalWorkSlot(slotId) {
  await withLocalWorkLock(() => {
    const entries = readLocalWorkSlots().filter((entry) => entry.id !== slotId);
    writeLocalWorkSlots(entries);
    return null;
  });
}

function readLocalWorkSlots() {
  const raw = localStorage.getItem(LOCAL_WORK_STATE_KEY);
  let entries = [];
  if (raw) {
    try {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) {
        entries = parsed;
      }
    } catch (_error) {
      entries = [];
    }
  }
  const now = Date.now();
  return entries.filter((entry) => entry && entry.id && Number(entry.createdAt) > now - LOCAL_WORK_SLOT_TTL_MS);
}

function writeLocalWorkSlots(entries) {
  localStorage.setItem(LOCAL_WORK_STATE_KEY, JSON.stringify(entries));
}

async function withLocalWorkLock(fn) {
  const lockId = `${LOCAL_WORK_TAB_ID}:${Date.now()}:${Math.random().toString(36).slice(2, 8)}`;
  while (true) {
    const now = Date.now();
    const raw = localStorage.getItem(LOCAL_WORK_LOCK_KEY);
    if (raw) {
      try {
        const lock = JSON.parse(raw);
        if (lock && Number(lock.expiresAt) > now && lock.id !== lockId) {
          await wait(25);
          continue;
        }
      } catch (_error) {
        // Ignore malformed lock and take over below.
      }
    }
    localStorage.setItem(
      LOCAL_WORK_LOCK_KEY,
      JSON.stringify({ id: lockId, expiresAt: now + LOCAL_WORK_LOCK_TTL_MS })
    );
    try {
      const verify = JSON.parse(localStorage.getItem(LOCAL_WORK_LOCK_KEY) || "{}");
      if (verify.id !== lockId) {
        await wait(25);
        continue;
      }
      return fn();
    } finally {
      const current = localStorage.getItem(LOCAL_WORK_LOCK_KEY);
      try {
        const parsed = current ? JSON.parse(current) : {};
        if (parsed.id === lockId) {
          localStorage.removeItem(LOCAL_WORK_LOCK_KEY);
        }
      } catch (_error) {
        localStorage.removeItem(LOCAL_WORK_LOCK_KEY);
      }
    }
  }
}

function wait(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function persistSessionState() {
  if (sessionPersistTimer) {
    window.clearTimeout(sessionPersistTimer);
  }
  sessionPersistTimer = window.setTimeout(() => {
    sessionPersistTimer = 0;
    flushPersistSessionState();
  }, SESSION_PERSIST_DEBOUNCE_MS);
}

function flushPersistSessionState() {
  if (sessionPersistTimer) {
    window.clearTimeout(sessionPersistTimer);
    sessionPersistTimer = 0;
  }
  const payload = getWorkspaceSnapshot();
  try {
    window.sessionStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(payload));
  } catch (_error) {
    // Ignore storage failures.
  }
  window.dispatchEvent(new CustomEvent("specbot:workspace-persisted", { detail: payload }));
}

function getWorkspaceSnapshot() {
  return {
    activeSpecNo: state.activeSpecNo,
    loadedRoots: state.loadedRoots,
    expandedKeys: [...state.ui.expandedKeys],
    focusedKey: state.ui.focusedKey,
    viewportKey: state.ui.viewportKey,
    collapsedSpecs: [...state.ui.collapsedSpecs],
    collapsedLoadedSpecs: [...state.ui.collapsedLoadedSpecs],
    clauseQuery: state.ui.clauseQuery,
    specbotQueryText: state.ui.specbotQueryText || "",
    specbotSettings: state.ui.specbotSettings,
    boardScope: state.ui.boardScope,
    specbotResults: state.ui.specbotResults,
    notes: state.ui.notes || [],
    highlights: state.ui.highlights || [],
  };
}

function restoreSessionState() {
  try {
    const raw = window.sessionStorage.getItem(SESSION_STORAGE_KEY);
    if (!raw) {
      return;
    }
    const payload = JSON.parse(raw);
    state.activeSpecNo = payload.activeSpecNo || "";
    state.loadedRoots = ensureForestStableBlockIds(Array.isArray(payload.loadedRoots) ? payload.loadedRoots : []);
    state.ui.expandedKeys = new Set(Array.isArray(payload.expandedKeys) ? payload.expandedKeys : []);
    state.ui.focusedKey = payload.focusedKey || "";
    state.ui.viewportKey = payload.viewportKey || "";
    state.ui.collapsedSpecs = new Set(Array.isArray(payload.collapsedSpecs) ? payload.collapsedSpecs : []);
    state.ui.collapsedLoadedSpecs = new Set(
      Array.isArray(payload.collapsedLoadedSpecs) ? payload.collapsedLoadedSpecs : []
    );
    state.ui.clauseQuery = payload.clauseQuery || "";
    state.ui.specbotQueryText = payload.specbotQueryText || "";
    state.ui.notes = Array.isArray(payload.notes) ? payload.notes : [];
    state.ui.highlights = Array.isArray(payload.highlights) ? payload.highlights : [];
    syncAllAnnotationBlockReferences();
    if (payload.specbotSettings && typeof payload.specbotSettings === "object") {
      state.ui.specbotSettings = {
        ...payload.specbotSettings,
        rejectedClauses: getNormalizedRejectedClauses(payload.specbotSettings.rejectedClauses),
      };
    }
    if (payload.boardScope && typeof payload.boardScope === "object") {
      state.ui.boardScope = {
        releaseData: String(payload.boardScope.releaseData || "").trim(),
        release: String(payload.boardScope.release || "").trim(),
      };
    }
    state.ui.specbotResults = Array.isArray(payload.specbotResults) ? [...payload.specbotResults].sort(compareSpecbotHits) : [];
  } catch (_error) {
    // Ignore malformed saved state.
  }
}

async function applyWorkspaceSnapshot(payload) {
  state.activeSpecNo = payload?.activeSpecNo || "";
  state.loadedRoots = ensureForestStableBlockIds(Array.isArray(payload?.loadedRoots) ? payload.loadedRoots : []);
  state.ui.expandedKeys = new Set(Array.isArray(payload?.expandedKeys) ? payload.expandedKeys : []);
  state.ui.focusedKey = payload?.focusedKey || "";
  state.ui.viewportKey = payload?.viewportKey || "";
  state.ui.collapsedSpecs = new Set(Array.isArray(payload?.collapsedSpecs) ? payload.collapsedSpecs : []);
  state.ui.collapsedLoadedSpecs = new Set(Array.isArray(payload?.collapsedLoadedSpecs) ? payload.collapsedLoadedSpecs : []);
  state.ui.clauseQuery = payload?.clauseQuery || "";
  state.ui.specbotQueryText = payload?.specbotQueryText || "";
  state.ui.notes = Array.isArray(payload?.notes) ? payload.notes : [];
  state.ui.highlights = Array.isArray(payload?.highlights) ? payload.highlights : [];
  syncAllAnnotationBlockReferences();
  state.ui.specbotResults = Array.isArray(payload?.specbotResults) ? [...payload.specbotResults].sort(compareSpecbotHits) : [];
  state.ui.boardScope = {
    releaseData: String(payload?.boardScope?.releaseData || "").trim(),
    release: String(payload?.boardScope?.release || "").trim(),
  };
  if (payload?.specbotSettings && typeof payload.specbotSettings === "object") {
    state.ui.specbotSettings = {
      ...payload.specbotSettings,
      rejectedClauses: getNormalizedRejectedClauses(payload.specbotSettings.rejectedClauses),
    };
  }
  if (state.activeSpecNo) {
    await ensureClauseCatalog(state.activeSpecNo);
  }
  if (elements.activeDocumentLabel) {
    elements.activeDocumentLabel.textContent = state.activeSpecNo || "문서를 선택하세요";
  }
  if (elements.clauseSearch) {
    elements.clauseSearch.value = state.ui.clauseQuery || "";
  }
  if (elements.specbotQuery) {
    elements.specbotQuery.value = state.ui.specbotQueryText || "";
  }
  persistSessionState();
  renderLoadedTree();
  renderSelectedClauseList();
  renderSpecbotResults();
  renderClauseTree();
}

async function resetWorkspace() {
  await applyWorkspaceSnapshot({
    activeSpecNo: "",
    loadedRoots: [],
    expandedKeys: [],
    focusedKey: "",
    viewportKey: "",
    collapsedSpecs: [],
    collapsedLoadedSpecs: [],
    clauseQuery: "",
    specbotQueryText: "",
    notes: [],
    highlights: [],
    specbotResults: [],
    specbotSettings: state.ui.specbotSettings,
    boardScope: state.ui.boardScope,
  });
}

export {
  state,
  elements,
  bindElements,
  bindGlobalEvents,
  loadConfig,
  getBoardScope,
  setBoardScope,
  refreshDocuments,
  restoreSessionState,
  ensureClauseCatalog,
  renderLoadedTree,
  renderSelectedClauseList,
  renderSpecbotResults,
  renderClauseTree,
  openPicker,
  runSpecbotQuery,
  clearSpecbotResults,
  openSpecbotSettings,
  saveSpecbotSettings,
  clearRejectedSpecbotClauses,
  exportDocx,
  openNoticeModal,
  clearMessage,
  runSelectionAction,
  toggleSelectionHighlight,
  addManualSelectionNote,
  getWorkspaceSnapshot,
  applyWorkspaceSnapshot,
  resetWorkspace,
  handleSelectionChange,
  hideSelectionMenu,
  hideNodeMenu,
  addParentClause,
  setAllSpecbotDocuments,
  debounce,
  removeTableRowFromCells,
  removeTableColumnFromCells,
  deriveNodeTextFromBlocks,
};
