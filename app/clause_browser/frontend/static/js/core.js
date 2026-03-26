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
    selection: {
      text: "",
      clauseKey: "",
      clauseLabel: "",
    },
    results: [],
    nodeMenu: {
      key: "",
      x: 0,
      y: 0,
    },
  },
};

const elements = {};
const SESSION_STORAGE_KEY = "specbot-clause-browser-state-v2";

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
  elements.exportTitle = document.getElementById("export-title");
  elements.exportButton = document.getElementById("export-button");
  elements.selectedText = document.getElementById("selected-text");
  elements.selectionMeta = document.getElementById("selection-meta");
  elements.actionType = document.getElementById("action-type");
  elements.sourceLanguage = document.getElementById("source-language");
  elements.targetLanguage = document.getElementById("target-language");
  elements.runActionButton = document.getElementById("run-action-button");
  elements.resultList = document.getElementById("result-list");
  elements.selectionMenu = document.getElementById("selection-menu");
  elements.nodeMenu = document.getElementById("node-menu");
  elements.nodeMenuAddParent = document.getElementById("node-menu-add-parent");
  elements.specbotSettingsModal = document.getElementById("specbot-settings-modal");
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
  });
}

async function loadConfig() {
  const response = await apiGet("/api/clause-browser/config");
  state.config = response.data;
  populateSelect(elements.actionType, state.config.actions.map((item) => ({ value: item.type, label: item.label })));
  populateSelect(elements.sourceLanguage, state.config.languages.map((item) => ({ value: item.code, label: item.label })));
  populateSelect(elements.targetLanguage, state.config.languages.map((item) => ({ value: item.code, label: item.label })));
  elements.sourceLanguage.value = "en";
  elements.targetLanguage.value = "ko";
  state.ui.specbotSettings = { ...response.data.specbotDefaults };
  applySpecbotSettingsToForm();
}

async function refreshDocuments() {
  const query = encodeURIComponent(elements.documentSearch.value.trim());
  const response = await apiGet(`/api/clause-browser/documents?query=${query}`);
  state.documents = response.data.items;
  renderDocuments();
  if (state.ui.isSpecbotSettingsOpen) {
    renderSpecbotDocumentSettings();
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
        <article class="list-card ${activeClass}" data-spec-no="${escapeHtml(item.specNo)}">
          <h3>${escapeHtml(item.specNo)} <span class="muted">${escapeHtml(item.specTitle || "")}</span></h3>
          <div class="muted">${item.clauseCount} clauses · ${item.topLevelClauseCount} top-level</div>
          <button class="ghost" data-action="select-document" data-spec-no="${escapeHtml(item.specNo)}">이 문서 선택</button>
        </article>
      `;
    })
    .join("");

  elements.documentList.querySelectorAll("[data-action='select-document']").forEach((button) => {
    button.addEventListener("click", async () => {
      await selectDocument(button.dataset.specNo);
    });
  });
}

async function selectDocument(specNo) {
  state.activeSpecNo = specNo;
  state.ui.clauseQuery = "";
  elements.clauseSearch.value = "";
  elements.clauseSearch.disabled = false;
  elements.activeDocumentLabel.textContent = specNo;
  elements.pickerTitle.textContent = `${specNo} 문서 검색`;
  persistSessionState();
  updateClauseTreeSummary();
  try {
    await ensureClauseCatalog(specNo);
    renderDocuments();
    renderClauseTree();
  } catch (error) {
    setMessage(error.message, true);
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
    elements.clauseTreeList.innerHTML = '<div class="muted">먼저 왼쪽 버튼으로 문서를 검색하고 선택하세요.</div>';
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
  const haystack = [item.clauseId, item.clauseTitle, item.textPreview || "", (item.clausePath || []).join(" ")].join(" ").toLowerCase();
  if (haystack.includes(query)) {
    return true;
  }
  return (catalog.childrenByParent[clauseId] || []).some((childId) => branchMatchesQuery(childId, catalog, query));
}

function updateClauseTreeSummary(visibleRootCount = null) {
  if (!state.activeSpecNo) {
    elements.pickerSelectionSummary.textContent = "문서를 먼저 선택하세요.";
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
  const key = `${specNo}:${clauseId}`;
  const existing = findNodeByKey(key);
  if (existing) {
    closePicker();
    focusNode(key);
    setMessage(`이미 로드된 절입니다. ${clauseId} 위치로 이동했습니다.`, false);
    return existing;
  }

  const loadedAncestor = findLoadedAncestor(specNo, clauseId);
  if (loadedAncestor) {
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
    persistSessionState();
    closePicker();
    focusNode(subtree.key);
    renderLoadedTree();
    renderSelectedClauseList();
    renderClauseTree();
    setMessage(`${clauseId} 절과 하위 절을 불러왔습니다.`, false);
    return subtree;
  } catch (error) {
    setMessage(error.message, true);
    return null;
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
          <button class="icon-button ghost" title="포커스" aria-label="포커스" data-action="focus-node" data-node-key="${escapeHtml(node.key)}">◎</button>
          <button class="icon-button danger" title="이 절 제거" aria-label="이 절 제거" data-action="remove-node" data-node-key="${escapeHtml(node.key)}">✕</button>
        </div>
      </div>
      ${bodyHtml}
    </article>
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
        const paragraphClass = getParagraphClass(block.text || "");
        return `<p class="${paragraphClass}" data-clause-key="${escapeHtml(node.key)}" data-block-index="${index}">${escapeHtml(
          block.text || ""
        )}</p>`;
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
      updateSelectionState(selectedText, paragraph.dataset.clauseKey || "", getLabelForKey(paragraph.dataset.clauseKey || ""));
      showSelectionMenu(event.clientX, event.clientY);
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
  updateSelectionState(text, anchorElement.dataset.clauseKey || "", getLabelForKey(anchorElement.dataset.clauseKey || ""));
}

function updateSelectionState(text, clauseKey, clauseLabel) {
  state.ui.selection = { text, clauseKey, clauseLabel };
  elements.selectedText.value = text;
  elements.selectionMeta.textContent = clauseLabel ? `선택 위치: ${clauseLabel}` : "선택된 텍스트";
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

async function runAction() {
  const text = state.ui.selection.text || elements.selectedText.value.trim();
  if (!text) {
    setMessage("번역할 텍스트를 먼저 선택하세요.", true);
    return;
  }

  try {
    const response = await apiPost("/api/clause-browser/llm-actions", {
      actionType: elements.actionType.value,
      text,
      sourceLanguage: elements.sourceLanguage.value,
      targetLanguage: elements.targetLanguage.value,
      context: state.ui.selection.clauseLabel,
    });
    state.ui.results = [response.data, ...state.ui.results];
    renderResults();
    setMessage(`LLM 액션 완료: ${response.data.actionType}`, false);
  } catch (error) {
    setMessage(error.message, true);
  }
}

function renderResults() {
  if (!state.ui.results.length) {
    elements.resultList.innerHTML = '<div class="muted">결과가 여기에 쌓입니다.</div>';
    return;
  }

  elements.resultList.innerHTML = state.ui.results
    .map(
      (item) => `
      <article class="result-card">
        <div class="section-heading">
          <strong>${escapeHtml(item.actionType)}</strong>
          <span class="muted">${escapeHtml(item.provider)} / ${escapeHtml(item.model)}</span>
        </div>
        <div class="muted">${escapeHtml(item.sourceLanguage)} → ${escapeHtml(item.targetLanguage)}</div>
        <pre>${escapeHtml(item.outputText)}</pre>
      </article>
    `
    )
    .join("");
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
            <button class="ghost" data-action="load-specbot-hit" data-spec-no="${escapeHtml(item.specNo)}" data-clause-id="${escapeHtml(item.clauseId)}">이 절 추가</button>
            <button class="danger" data-action="reject-specbot-hit" data-spec-no="${escapeHtml(item.specNo)}" data-clause-id="${escapeHtml(item.clauseId)}">거절</button>
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
  const query = elements.specbotQuery.value.trim();
  state.ui.specbotQueryText = query;
  persistSessionState();
  if (!query) {
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
    setMessage(error.message, true);
  } finally {
    setSpecbotQueryLoading(false);
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
  if (!state.loadedRoots.length) {
    setMessage("저장할 절이 없습니다.", true);
    return;
  }
  const title = elements.exportTitle.value.trim();
  if (!title) {
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
    setMessage(error.message, true);
  }
}

function setMessage(text, isError) {
  const message = formatErrorMessage(text);
  state.ui.message = { text: message, isError };
  elements.messageBar.innerHTML = message ? `<div class="message ${isError ? "error" : ""}">${escapeHtml(message)}</div>` : "";
}

async function apiGet(url) {
  const response = await fetch(url);
  const payload = await parseResponse(response);
  if (!response.ok) {
    throw new Error(formatErrorMessage(payload.detail || payload || "Request failed"));
  }
  return payload;
}

async function apiPost(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const payload = await parseResponse(response);
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
  renderResults,
  renderSpecbotResults,
  renderClauseTree,
  openPicker,
  runSpecbotQuery,
  clearSpecbotResults,
  openSpecbotSettings,
  saveSpecbotSettings,
  clearRejectedSpecbotClauses,
  exportDocx,
  runAction,
  handleSelectionChange,
  hideSelectionMenu,
  hideNodeMenu,
  addParentClause,
  setAllSpecbotDocuments,
  debounce,
};
