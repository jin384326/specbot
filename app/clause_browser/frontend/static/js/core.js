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
    message: null,
    clauseQuery: "",
    specbotQueryText: "",
    specbotSettings: {},
    specbotResults: [],
    notes: [],
    busy: null,
    translationJob: null,
    selection: {
      text: "",
      clauseKey: "",
      clauseLabel: "",
      blockIndex: -1,
    },
    nodeMenu: {
      key: "",
      x: 0,
      y: 0,
    },
  },
};

const elements = {};
const SESSION_STORAGE_KEY = "specbot-clause-browser-state-v6";
const TRANSLATION_CHUNK_LIMIT = 12000;
const SPECBOT_QUERY_BUSY_LABEL = "SpecBot query 수행 중입니다.";
const DOCUMENT_SEARCH_BUSY_LABEL = "문서 검색 중입니다.";
const DOCUMENT_SELECT_BUSY_LABEL = "문서를 불러오는 중입니다.";
const activeRequestControllers = new Set();

function bindElements() {
  elements.openPickerButton = document.getElementById("open-picker-button");
  elements.specbotQuery = document.getElementById("specbot-query");
  elements.runSpecbotQuery = document.getElementById("run-specbot-query");
  elements.specbotSpinner = document.getElementById("specbot-spinner");
  elements.runSpecbotLabel = document.getElementById("run-specbot-label");
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
  elements.settingAutoExcludeLoaded = document.getElementById("setting-auto-exclude-loaded");
  elements.settingExcludeSpecs = document.getElementById("setting-exclude-specs");
  elements.settingExcludeClauses = document.getElementById("setting-exclude-clauses");
  elements.saveSpecbotSettings = document.getElementById("save-specbot-settings");
}

function bindGlobalEvents() {
  elements.treeContainer.addEventListener("scroll", debounce(syncViewportSelection, 40));
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
  });
  window.addEventListener("pagehide", abortActiveRequests);
  window.addEventListener("beforeunload", abortActiveRequests);
}

async function loadConfig() {
  const response = await apiGet("/api/clause-browser/config");
  state.config = response.data;
  state.ui.specbotSettings = { ...response.data.specbotDefaults };
  applySpecbotSettingsToForm();
}

async function refreshDocuments(options = {}) {
  if (!beginBusy("문서 검색 중입니다.", { ...options, allowDuringSpecbotQuery: true })) {
    return;
  }
  const query = encodeURIComponent(elements.documentSearch.value.trim());
  const clauseQuery = encodeURIComponent((elements.clauseSearch?.value || "").trim());
  try {
    const response = await apiGet(`/api/clause-browser/documents?query=${query}&clauseQuery=${clauseQuery}`);
    state.documents = response.data.items;
    renderDocuments();
    if (state.ui.isSpecbotSettingsOpen) {
      renderSpecbotDocumentSettings();
    }
  } finally {
    endBusy(options);
  }
}

function openPicker() {
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

function openSpecbotSettings() {
  applySpecbotSettingsToForm();
  renderSpecbotDocumentSettings();
  renderRejectedSpecbotClauses();
  state.ui.isSpecbotSettingsOpen = true;
  persistSessionState();
  elements.specbotSettingsModal.classList.remove("hidden");
}

function closeSpecbotSettings() {
  state.ui.isSpecbotSettingsOpen = false;
  persistSessionState();
  elements.specbotSettingsModal.classList.add("hidden");
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

function applySpecbotSettingsToForm() {
  const settings = state.ui.specbotSettings;
  elements.settingBaseUrl.value = settings.baseUrl || "";
  elements.settingConfigBaseUrl.value = settings.configBaseUrl || "";
  elements.settingLimit.value = settings.limit ?? 4;
  elements.settingIterations.value = settings.iterations ?? 2;
  elements.settingNextIterationLimit.value = settings.nextIterationLimit ?? 2;
  elements.settingFollowupMode.value = settings.followupMode || "sentence-summary";
  elements.settingSummary.value = settings.summary || "short";
  elements.settingRegistry.value = settings.registry || "";
  elements.settingLocalModelDir.value = settings.localModelDir || "";
  elements.settingDevice.value = settings.device || "cuda";
  elements.settingSparseBoost.value = settings.sparseBoost ?? 0;
  elements.settingVectorBoost.value = settings.vectorBoost ?? 1;
  elements.settingAutoExcludeLoaded.checked = settings.autoExcludeLoaded !== false;
  elements.settingExcludeSpecs.value = Array.isArray(settings.excludeSpecs) ? settings.excludeSpecs.join("\n") : "";
  elements.settingExcludeClauses.value = Array.isArray(settings.excludeClauses)
    ? settings.excludeClauses.map((item) => `${item.specNo}:${item.clauseId}`).join("\n")
    : "";
}

function saveSpecbotSettings() {
  const rejectedClauses = getRejectedSpecbotClauses();
  state.ui.specbotSettings = {
    baseUrl: elements.settingBaseUrl.value.trim(),
    configBaseUrl: elements.settingConfigBaseUrl.value.trim(),
    limit: Number(elements.settingLimit.value),
    iterations: Number(elements.settingIterations.value),
    nextIterationLimit: Number(elements.settingNextIterationLimit.value),
    followupMode: elements.settingFollowupMode.value,
    summary: elements.settingSummary.value.trim(),
    registry: elements.settingRegistry.value.trim(),
    localModelDir: elements.settingLocalModelDir.value.trim(),
    device: elements.settingDevice.value.trim(),
    sparseBoost: Number(elements.settingSparseBoost.value),
    vectorBoost: Number(elements.settingVectorBoost.value),
    includedSpecs: getSelectedSpecbotDocuments(),
    autoExcludeLoaded: elements.settingAutoExcludeLoaded.checked,
    excludeSpecs: parseSpecbotExcludeSpecs(elements.settingExcludeSpecs.value),
    excludeClauses: parseSpecbotExcludeClauses(elements.settingExcludeClauses.value),
    rejectedClauses,
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

  const response = await apiGet(
    `/api/clause-browser/documents/${encodeURIComponent(specNo)}/clauses?includeAll=true&limit=5000`
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
  if (!beginBusy("절을 불러오는 중입니다.")) {
    return null;
  }
  const key = `${specNo}:${clauseId}`;
  const existing = findNodeByKey(key);
  if (existing) {
    endBusy();
    closePicker();
    focusNode(key);
    setMessage(`이미 로드된 절입니다. ${clauseId} 위치로 이동했습니다.`, false);
    return existing;
  }

  const loadedAncestor = findLoadedAncestor(specNo, clauseId);
  if (loadedAncestor) {
    endBusy();
    closePicker();
    focusNode(loadedAncestor.key);
    setMessage(`이미 로드된 상위 절에 포함되어 있습니다. ${loadedAncestor.clauseId} 위치로 이동했습니다.`, false);
    return loadedAncestor;
  }

  try {
    const response = await apiGet(
      `/api/clause-browser/documents/${encodeURIComponent(specNo)}/clauses/${encodeURIComponent(clauseId)}/subtree`
    );
    const subtree = response.data;
    expandAll(subtree);
    state.loadedRoots = mergeLoadedRoot(state.loadedRoots, subtree);
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
    endBusy();
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
  elements.treeContainer.innerHTML = sortedRoots.map((node) => renderNode(node)).join("");
  bindTreeEvents();
  syncViewportSelection();
}

function renderNode(node) {
  const expanded = state.ui.expandedKeys.has(node.key);
  const focusedClass = state.ui.focusedKey === node.key ? "focused" : "";
  const notesHtml = renderClauseNotes(node.key);
  const clauseNoteToggleHtml = renderClauseNoteToggle(node.key);
  const childrenHtml =
    expanded && (node.children || []).length
      ? `<div class="tree-children">${node.children.map((child) => renderNode(child)).join("")}</div>`
      : "";
  const bodyHtml = expanded
    ? `
      <div class="tree-body">
        ${renderBlocks(node)}
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
          <button class="icon-button danger" title="이 절 제거" aria-label="이 절 제거" data-action="remove-node" data-node-key="${escapeHtml(node.key)}">✕</button>
        </div>
      </div>
      ${bodyHtml}
      ${notesHtml}
    </article>
  `;
}

function renderTranslationStatus() {
  const job = state.ui.translationJob;
  if (!job || !job.totalRequests) {
    elements.translationStatus.classList.add("hidden");
    elements.translationStatus.innerHTML = "";
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
        const cellRows = block.cells || [];
        const rows = block.rows || [];
        const tableBody =
          cellRows.length
            ? cellRows
                .map(
                  (row) => `
                    <tr>
                      ${row
                        .map((cell) => {
                          const tag = cell.header ? "th" : "td";
                          const rowspan = Number(cell.rowspan || 1) > 1 ? ` rowspan="${Number(cell.rowspan || 1)}"` : "";
                          const colspan = Number(cell.colspan || 1) > 1 ? ` colspan="${Number(cell.colspan || 1)}"` : "";
                          return `<${tag} class="tree-text" data-clause-key="${escapeHtml(node.key)}"${rowspan}${colspan}>${escapeHtml(
                            cell.text || ""
                          )}</${tag}>`;
                        })
                        .join("")}
                    </tr>
                  `
                )
                .join("")
            : rows
                .map(
                  (row, rowIndex) => `
                    <tr>
                      ${row
                        .map((cell) =>
                          rowIndex === 0
                            ? `<th class="tree-text" data-clause-key="${escapeHtml(node.key)}">${escapeHtml(cell || "")}</th>`
                            : `<td class="tree-text" data-clause-key="${escapeHtml(node.key)}">${escapeHtml(cell || "")}</td>`
                        )
                        .join("")}
                    </tr>
                  `
                )
                .join("");
        return `
          <div class="docx-table-wrap" data-clause-key="${escapeHtml(node.key)}">
            <table class="docx-table">
              <tbody>
                ${tableBody}
              </tbody>
            </table>
          </div>
        `;
      }
      if (block.type === "image") {
        const src = block.src || "";
        const extension = src.split(".").pop()?.toLowerCase() || "";
        if (extension === "wmf" || extension === "emf") {
          const svgSrc = src.replace(/\.wmf$/i, ".svg").replace(/\.emf$/i, ".svg");
          return `
            <figure class="docx-figure">
              <img src="${escapeHtml(svgSrc)}" alt="${escapeHtml(block.alt || "")}" />
              <figcaption class="muted">${escapeHtml(block.alt || "Image")}</figcaption>
            </figure>
          `;
        }
        return `
          <figure class="docx-figure">
            <img src="${escapeHtml(src)}" alt="${escapeHtml(block.alt || "")}" />
            <figcaption class="muted">${escapeHtml(block.alt || "Image")}</figcaption>
          </figure>
        `;
      }
      return "";
    })
    .join("");
}

function renderParagraphBlock(node, block, index) {
  const paragraphClass = getParagraphClass(block.text || "");
  const selectionToggleHtml = renderSelectionNoteToggle(node.key, index);
  const selectionNotesHtml = renderSelectionNotes(node.key, index);
  return `
    <div class="paragraph-block">
      <div class="paragraph-note-row">
        <p class="${paragraphClass}" data-clause-key="${escapeHtml(node.key)}" data-block-index="${index}">${escapeHtml(block.text || "")}</p>
        ${selectionToggleHtml}
      </div>
      ${selectionNotesHtml}
    </div>
  `;
}

function renderClauseNotes(clauseKey) {
  const notes = getNotesForClause(clauseKey).filter((note) => note.type === "clause");
  if (!notes.length) {
    return "";
  }
  const visibleNotes = notes.filter((note) => !note.collapsed);
  if (!visibleNotes.length) {
    return "";
  }
  return `
    <div class="clause-note-list">
      ${visibleNotes
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
              <div class="clause-note-body ${note.collapsed ? "hidden" : ""}">
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
  const expanded = notes.some((note) => !note.collapsed);
  return `
    <button
      class="icon-button ghost note-toggle-button"
      title="절 메모 ${expanded ? "접기" : "펼치기"}"
      aria-label="절 메모 ${expanded ? "접기" : "펼치기"}"
      data-action="toggle-clause-notes"
      data-clause-key="${escapeHtml(clauseKey)}"
    >
      📝
    </button>
  `;
}

function renderSelectionNoteToggle(clauseKey, blockIndex) {
  const notes = getSelectionNotesForBlock(clauseKey, blockIndex);
  if (!notes.length) {
    return "";
  }
  const expanded = notes.some((note) => !note.collapsed);
  return `
    <button
      class="selection-note-toggle ghost"
      title="선택 메모 ${notes.length}개"
      aria-label="선택 메모 ${notes.length}개"
      data-action="toggle-selection-notes"
      data-clause-key="${escapeHtml(clauseKey)}"
      data-block-index="${blockIndex}"
    >
      📝 ${notes.length}
    </button>
  `;
}

function renderSelectionNotes(clauseKey, blockIndex) {
  const notes = getSelectionNotesForBlock(clauseKey, blockIndex);
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

function bindTreeEvents() {
  elements.treeContainer.querySelectorAll("[data-action='toggle-node']").forEach((button) => {
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

  elements.treeContainer.querySelectorAll("[data-action='remove-node']").forEach((button) => {
    button.addEventListener("click", () => {
      const key = button.dataset.nodeKey;
      const target = findNodeByKey(key);
      if (!target) {
        return;
      }
      pruneNotesForNodeKey(key);
      state.loadedRoots = removeNodeFromForest(state.loadedRoots, key);
      if (state.ui.focusedKey === key) {
        state.ui.focusedKey = "";
      }
      persistSessionState();
      renderLoadedTree();
      renderSelectedClauseList();
      renderClauseTree();
      setMessage(`${target.clauseId} 절과 하위 절을 제거했습니다.`, false);
    });
  });

  elements.treeContainer.querySelectorAll("[data-action='focus-node']").forEach((button) => {
    button.addEventListener("click", () => {
      focusNode(button.dataset.nodeKey);
    });
  });

  elements.treeContainer.querySelectorAll(".tree-header").forEach((header) => {
    header.addEventListener("contextmenu", (event) => {
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

  elements.treeContainer.querySelectorAll(".tree-text").forEach((paragraph) => {
    paragraph.addEventListener("contextmenu", (event) => {
      const selection = window.getSelection();
      const selectedText = selection ? selection.toString().trim() : "";
      if (!selectedText) {
        return;
      }
      event.preventDefault();
      hideNodeMenu();
      updateSelectionState(
        selectedText,
        paragraph.dataset.clauseKey || "",
        getLabelForKey(paragraph.dataset.clauseKey || ""),
        Number(paragraph.dataset.blockIndex || -1)
      );
      showSelectionMenu(event.clientX, event.clientY);
    });
  });

  elements.treeContainer.querySelectorAll("[data-action='translate-clause']").forEach((button) => {
    button.addEventListener("click", async () => {
      await runClauseTranslation(button.dataset.nodeKey || "");
    });
  });

  elements.treeContainer.querySelectorAll("[data-action='toggle-clause-notes']").forEach((button) => {
    button.addEventListener("click", () => {
      toggleClauseNotes(button.dataset.clauseKey || "");
    });
  });

  elements.treeContainer.querySelectorAll("[data-action='edit-note-translation']").forEach((textarea) => {
    textarea.addEventListener("input", (event) => {
      updateNoteField(textarea.dataset.noteId || "", "translation", event.target.value);
    });
  });

  elements.treeContainer.querySelectorAll("[data-action='toggle-selection-notes']").forEach((button) => {
    button.addEventListener("click", () => {
      toggleSelectionNotes(button.dataset.clauseKey || "", Number(button.dataset.blockIndex || -1));
    });
  });

  elements.treeContainer.querySelectorAll("[data-action='delete-note']").forEach((button) => {
    button.addEventListener("click", () => {
      deleteNote(button.dataset.noteId || "");
    });
  });

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
  state.ui.focusedKey = key;
  state.ui.viewportKey = key;
  persistSessionState();
  renderLoadedTree();
  renderSelectedClauseList();
  window.setTimeout(() => {
    const element = document.getElementById(`node-${escapeKey(key)}`);
    element?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, 0);
}

async function addParentClause(nodeKey) {
  if (state.ui.busy) {
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
  ensureSelectedClauseVisible();
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

function isCaptionParagraph(text) {
  return /^(Figure|Table)\s+[A-Za-z0-9.\-]+:/.test(String(text).trim());
}

function getParagraphClass(text) {
  const value = String(text).trim();
  if (isCaptionParagraph(value)) {
    return "tree-text docx-paragraph docx-caption";
  }
  if (/^NOTE\s*:/i.test(value)) {
    return "tree-text docx-paragraph docx-note";
  }
  if (/^(EXAMPLE|Examples?)\s*:/i.test(value)) {
    return "tree-text docx-paragraph docx-example";
  }
  if (/^(WARNING|CAUTION)\s*:/i.test(value)) {
    return "tree-text docx-paragraph docx-warning";
  }
  if (/^(Annex|APPENDIX)\b/i.test(value)) {
    return "tree-text docx-paragraph docx-annex";
  }
  if (/^(?:[-*•]|[A-Za-z]\)|\d+\)|\d+\.)\s+/.test(value)) {
    return "tree-text docx-paragraph docx-list";
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
      renderSelectedClauseList();
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
    renderSelectedClauseList();
  }
}

function ensureSelectedClauseVisible() {
  const active = elements.selectedClauseList.querySelector(".selected-clause-row.active");
  active?.scrollIntoView({ block: "nearest" });
}

function handleSelectionChange() {
  const selection = window.getSelection();
  const text = selection ? selection.toString().trim() : "";
  if (!text) {
    hideSelectionMenu();
    return;
  }
  const anchorElement = selection.anchorNode?.parentElement?.closest(".tree-text");
  if (!anchorElement) {
    return;
  }
  updateSelectionState(
    text,
    anchorElement.dataset.clauseKey || "",
    getLabelForKey(anchorElement.dataset.clauseKey || "")
  );
}

function updateSelectionState(text, clauseKey, clauseLabel, blockIndex = -1) {
  state.ui.selection = { text, clauseKey, clauseLabel, blockIndex };
}

function getLabelForKey(key) {
  const node = findNodeByKey(key);
  return node ? `${node.specNo} / ${node.clauseId} ${node.clauseTitle}` : "";
}

function showSelectionMenu(x, y) {
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
  try {
    await createTranslatedNote({
      type: "selection",
      clauseKey: state.ui.selection.clauseKey,
      blockIndex: state.ui.selection.blockIndex,
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
    }, 1200);
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
      for (let start = 0; start < paragraph.length; start += limit) {
        chunks.push(paragraph.slice(start, start + limit).trim());
      }
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

async function createTranslatedNote({ type, clauseKey, blockIndex = -1, sourceText, clauseLabel, targetLanguage }) {
  try {
    const sourceLanguage = inferSourceLanguage(sourceText);
    const response = await apiPost("/api/clause-browser/llm-actions", {
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
      blockIndex,
      clauseLabel,
      sourceText,
      translation: response.data.outputText,
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
  }
}

function getNotesForClause(clauseKey) {
  return (state.ui.notes || []).filter((note) => note.clauseKey === clauseKey);
}

function getSelectionNotesForBlock(clauseKey, blockIndex) {
  return (state.ui.notes || []).filter(
    (note) => note.type === "selection" && note.clauseKey === clauseKey && Number(note.blockIndex) === Number(blockIndex)
  );
}

function upsertNote(note) {
  const existingIndex = (state.ui.notes || []).findIndex((item) => item.id === note.id);
  if (existingIndex >= 0) {
    state.ui.notes = state.ui.notes.map((item, index) => (index === existingIndex ? { ...item, ...note } : item));
  } else {
    state.ui.notes = [note, ...(state.ui.notes || [])];
  }
  persistSessionState();
  renderLoadedTree();
}

function updateNoteField(noteId, field, value) {
  state.ui.notes = (state.ui.notes || []).map((note) => (note.id === noteId ? { ...note, [field]: value } : note));
  persistSessionState();
}

function toggleClauseNotes(clauseKey) {
  const notes = getNotesForClause(clauseKey).filter((note) => note.type === "clause");
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

function toggleSelectionNotes(clauseKey, blockIndex) {
  const notes = getSelectionNotesForBlock(clauseKey, blockIndex);
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
  state.ui.notes = (state.ui.notes || []).filter((note) => note.id !== noteId);
  persistSessionState();
  renderLoadedTree();
}

function pruneNotesForNodeKey(nodeKey) {
  const node = findNodeByKey(nodeKey);
  if (!node) {
    return;
  }
  const subtreeKeys = new Set(collectNodeKeys(node));
  state.ui.notes = (state.ui.notes || []).filter((note) => !subtreeKeys.has(note.clauseKey));
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
      await loadClauseFromSpec(button.dataset.specNo, button.dataset.clauseId);
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
  setSpecbotQueryLoading(true);
  try {
    const exclusions = buildSpecbotExclusions();
    const response = await apiPost("/api/clause-browser/specbot/query", {
      query,
      settings: state.ui.specbotSettings,
      excludeSpecs: exclusions.excludeSpecs,
      excludeClauses: exclusions.excludeClauses,
    });
    state.ui.specbotResults = filterSpecbotHitsByExclusions(response.data.hits || [], exclusions).sort(compareSpecbotHits);
    persistSessionState();
    renderSpecbotResults();
    setMessage(`SpecBot query 완료: ${query}`, false);
  } catch (error) {
    if (!isAbortedRequestError(error)) {
      setMessage(error.message, true);
    }
  } finally {
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

  if (settings.autoExcludeLoaded !== false) {
    collectLoadedClausePairs(state.loadedRoots).forEach((item) => {
      excludeClauseMap.set(`${item.specNo}:${item.clauseId}`, item);
    });
  }

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
  if (!docs.length) {
    elements.settingDocumentList.innerHTML = '<div class="muted">문서 목록을 불러오는 중입니다.</div>';
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
  elements.runSpecbotQuery.disabled = isLoading;
  elements.specbotQuery.disabled = isLoading;
  elements.specbotSpinner.classList.toggle("hidden", !isLoading);
  elements.runSpecbotLabel.textContent = isLoading ? "수행 중" : "수행";
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
  const title = elements.exportTitle.value.trim();
  if (!title) {
    endBusy();
    setMessage("DOCX 제목을 입력하세요.", true);
    return;
  }

  try {
    const response = await apiPost("/api/clause-browser/exports/docx", {
      title,
      roots: state.loadedRoots,
    });
    setMessage(`DOCX 저장 완료: ${response.data.relativePath}`, false);
    elements.exportTitle.value = "";
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
  elements.exportButton.disabled = isBusy;
  elements.openSpecbotSettings.disabled = isBusy;
  elements.runSpecbotQuery.disabled = isBusy;
  elements.specbotQuery.disabled = isBusy;
}

function setMessage(text, isError) {
  const message = formatErrorMessage(text);
  state.ui.message = { text: message, isError };
  elements.messageBar.innerHTML = message ? `<div class="message ${isError ? "error" : ""}">${escapeHtml(message)}</div>` : "";
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

function persistSessionState() {
  const payload = {
    activeSpecNo: state.activeSpecNo,
    loadedRoots: state.loadedRoots,
    expandedKeys: [...state.ui.expandedKeys],
    focusedKey: state.ui.focusedKey,
    viewportKey: state.ui.viewportKey,
    collapsedSpecs: [...state.ui.collapsedSpecs],
    clauseQuery: state.ui.clauseQuery,
    specbotQueryText: state.ui.specbotQueryText || "",
    specbotSettings: state.ui.specbotSettings,
    specbotResults: state.ui.specbotResults,
    notes: state.ui.notes || [],
  };
  try {
    window.sessionStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(payload));
  } catch (_error) {
    // Ignore storage failures.
  }
}

function restoreSessionState() {
  try {
    const raw = window.sessionStorage.getItem(SESSION_STORAGE_KEY);
    if (!raw) {
      return;
    }
    const payload = JSON.parse(raw);
    state.activeSpecNo = payload.activeSpecNo || "";
    state.loadedRoots = Array.isArray(payload.loadedRoots) ? payload.loadedRoots : [];
    state.ui.expandedKeys = new Set(Array.isArray(payload.expandedKeys) ? payload.expandedKeys : []);
    state.ui.focusedKey = payload.focusedKey || "";
    state.ui.viewportKey = payload.viewportKey || "";
    state.ui.collapsedSpecs = new Set(Array.isArray(payload.collapsedSpecs) ? payload.collapsedSpecs : []);
    state.ui.clauseQuery = payload.clauseQuery || "";
    state.ui.specbotQueryText = payload.specbotQueryText || "";
    state.ui.notes = Array.isArray(payload.notes) ? payload.notes : [];
    if (payload.specbotSettings && typeof payload.specbotSettings === "object") {
      state.ui.specbotSettings = {
        ...payload.specbotSettings,
        rejectedClauses: getNormalizedRejectedClauses(payload.specbotSettings.rejectedClauses),
      };
    }
    state.ui.specbotResults = Array.isArray(payload.specbotResults) ? [...payload.specbotResults].sort(compareSpecbotHits) : [];
  } catch (_error) {
    // Ignore malformed saved state.
  }
}

export {
  state,
  elements,
  bindElements,
  bindGlobalEvents,
  loadConfig,
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
  runSelectionAction,
  handleSelectionChange,
  hideSelectionMenu,
  hideNodeMenu,
  addParentClause,
  setAllSpecbotDocuments,
  debounce,
};
