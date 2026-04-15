export function createSpecbotController(dependencies) {
  const {
    state,
    elements,
    dedupeClausePairs,
    getNormalizedRejectedClauses,
    getIterationsForDepth,
    getSpecbotDepthFromSettings,
    parseSpecbotExcludeSpecs,
    parseSpecbotExcludeClauses,
    normalizeSpecbotDepth,
    buildSpecbotExclusionsFromState,
    filterSpecbotHitsByExclusionsFromState,
    buildSpecbotResultsHtml,
    buildSpecbotDocumentSettingsHtml,
    buildRejectedSpecbotClausesHtml,
    getSpecbotDocumentSelectionCount,
    getSpecbotQueryLoadingLabel,
    compareSpecbotHits,
    compareMixedToken,
    mergeSpecbotHits,
    escapeHtml,
    persistSessionState,
    setMessage,
    beginBusy,
    endBusy,
    getBoardScope,
    streamSpecbotQuery,
    isAbortedRequestError,
    loadClauseFromSpec,
    renderLoadedTree,
  } = dependencies;

  function getRejectedSpecbotClauses() {
    return getNormalizedRejectedClauses(state.ui.specbotSettings?.rejectedClauses);
  }

  function buildSpecbotExclusions() {
    return buildSpecbotExclusionsFromState({
      settings: state.ui.specbotSettings || {},
      documents: state.documents || [],
      loadedRoots: state.loadedRoots,
      rejectedClauses: getRejectedSpecbotClauses(),
      compareMixedToken,
      compareSpecbotHits,
    });
  }

  function filterSpecbotHitsByExclusions(hits, exclusions = buildSpecbotExclusions()) {
    return filterSpecbotHitsByExclusionsFromState(hits, exclusions);
  }

  function pruneSpecbotResultsByCurrentExclusions() {
    state.ui.specbotResults = filterSpecbotHitsByExclusions(state.ui.specbotResults, buildSpecbotExclusions()).sort(compareSpecbotHits);
  }

  function renderSpecbotResults() {
    const collapsed = Boolean(state.ui.specbotResultsCollapsed);
    if (elements.toggleSpecbotResults) {
      elements.toggleSpecbotResults.textContent = collapsed ? "+" : "−";
      elements.toggleSpecbotResults.title = collapsed ? "펼치기" : "접기";
      elements.toggleSpecbotResults.setAttribute("aria-label", collapsed ? "펼치기" : "접기");
    }
    elements.specbotResultList.classList.toggle("hidden", collapsed);
    elements.specbotResultList.setAttribute("aria-hidden", collapsed ? "true" : "false");
    if (collapsed) {
      return;
    }
    elements.specbotResultList.innerHTML = buildSpecbotResultsHtml(state.ui.specbotResults, escapeHtml);
    elements.specbotResultList.querySelectorAll("[data-action='load-specbot-hit']").forEach((button) => {
      button.addEventListener("click", async () => {
        const hit = state.ui.specbotResults.find(
          (item) =>
            String(item.specNo || "") === String(button.dataset.specNo || "") &&
            String(item.clauseId || "") === String(button.dataset.clauseId || "")
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

  function toggleSpecbotResultsPanel() {
    state.ui.specbotResultsCollapsed = !state.ui.specbotResultsCollapsed;
    persistSessionState();
    renderSpecbotResults();
  }

  function renderSpecbotDocumentSettings() {
    const docs = state.documents || [];
    if (state.ui.specbotDocumentSettingsLoading) {
      elements.settingDocumentList.innerHTML = '<div class="muted">문서 목록을 불러오는 중입니다.</div>';
      elements.settingDocumentSelectionCount.textContent = getSpecbotDocumentSelectionCount(0, 0);
      return;
    }
    const selectedSpecs = new Set(
      Array.isArray(state.ui.specbotSettings?.includedSpecs) && state.ui.specbotSettings.includedSpecs.length
        ? state.ui.specbotSettings.includedSpecs.map((item) => String(item).trim()).filter(Boolean)
        : docs.map((item) => String(item.specNo || "").trim()).filter(Boolean)
    );
    elements.settingDocumentList.innerHTML = buildSpecbotDocumentSettingsHtml(docs, selectedSpecs, escapeHtml);
    elements.settingDocumentList.querySelectorAll("[data-action='toggle-specbot-doc']").forEach((input) => {
      input.addEventListener("change", updateSpecbotDocumentSelectionCount);
    });
    updateSpecbotDocumentSelectionCount();
  }

  function renderRejectedSpecbotClauses() {
    const rejectedClauses = getRejectedSpecbotClauses();
    if (!rejectedClauses.length) {
      elements.settingRejectedClauseList.innerHTML = buildRejectedSpecbotClausesHtml([], escapeHtml);
      elements.settingClearRejectedClauses.disabled = true;
      return;
    }

    elements.settingClearRejectedClauses.disabled = false;
    elements.settingRejectedClauseList.innerHTML = buildRejectedSpecbotClausesHtml(
      rejectedClauses.sort(compareSpecbotHits),
      escapeHtml
    );

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
    elements.settingDocumentSelectionCount.textContent = getSpecbotDocumentSelectionCount(selectedCount, totalCount);
  }

  function setAllSpecbotDocuments(checked) {
    elements.settingDocumentList.querySelectorAll("[data-action='toggle-specbot-doc']").forEach((input) => {
      input.checked = checked;
    });
    updateSpecbotDocumentSelectionCount();
  }

  function setSpecbotQueryLoading(isLoading) {
    const label = !isLoading ? "" : getSpecbotQueryLoadingLabel(state.ui.specbotQueryStatus);
    elements.specbotQuery.disabled = isLoading;
    elements.specbotSpinner.classList.toggle("hidden", !isLoading);
    elements.runSpecbotLabel.textContent = label;
    elements.specbotQueryStatus.classList.toggle("hidden", !isLoading);
  }

  function applySpecbotDepthSelection(depth) {
    const normalizedDepth = normalizeSpecbotDepth(depth);
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

  async function runSpecbotQuery(busyLabel) {
    if (!beginBusy(busyLabel)) {
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
      state.ui.specbotSettings = {
        ...state.ui.specbotSettings,
        iterations: getIterationsForDepth(queryDepth),
        queryDepth,
      };
      persistSessionState();
      const scope = getBoardScope();
      const response = await streamSpecbotQuery({
        query,
        releaseData: scope.releaseData,
        release: scope.release,
        settings: {
          ...state.ui.specbotSettings,
          iterations: getIterationsForDepth(queryDepth),
          queryDepth,
        },
        excludeSpecs: exclusions.excludeSpecs,
        excludeClauses: exclusions.excludeClauses,
      });
      state.ui.specbotResults = mergeSpecbotHits(state.ui.specbotResults, response.hits || [], {
        exclusions,
        filterHitsByExclusions: filterSpecbotHitsByExclusions,
        compareHits: compareSpecbotHits,
      });
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

  function applySpecbotSettingsToForm() {
    const settings = state.ui.specbotSettings || {};
    elements.settingBaseUrl.value = settings.baseUrl || "";
    elements.settingConfigBaseUrl.value = settings.configBaseUrl || "";
    elements.settingLimit.value = settings.limit || 4;
    elements.settingIterations.value = settings.iterations ?? 1;
    elements.settingNextIterationLimit.value = settings.nextIterationLimit ?? 2;
    elements.settingFollowupMode.value = settings.followupMode || "sentence-summary";
    elements.settingSummary.value = settings.summary || "short";
    elements.settingRegistry.value = settings.registry || "";
    elements.settingLocalModelDir.value = settings.localModelDir || "";
    elements.settingDevice.value = settings.device || "cuda";
    elements.settingSparseBoost.value = settings.sparseBoost ?? 0;
    elements.settingVectorBoost.value = settings.vectorBoost ?? 1;
    applySpecbotDepthSelection(getSpecbotDepthFromSettings(settings));
    renderSpecbotDocumentSettings();
    renderRejectedSpecbotClauses();

    const rejectedClauses = getRejectedSpecbotClauses();
    elements.settingExcludeSpecs.value = Array.isArray(settings.excludeSpecs) ? settings.excludeSpecs.join("\n") : "";
    elements.settingExcludeClauses.value = Array.isArray(settings.excludeClauses)
      ? settings.excludeClauses.map((item) => `${item.specNo}:${item.clauseId}`).join("\n")
      : "";
    if (rejectedClauses.length && !elements.settingExcludeClauses.value.trim()) {
      elements.settingExcludeClauses.value = rejectedClauses.map((item) => `${item.specNo}:${item.clauseId}`).join("\n");
    }
  }

  function openSpecbotSettings() {
    state.ui.isSpecbotSettingsOpen = true;
    elements.specbotSettingsModal.classList.remove("hidden");
    elements.specbotSettingsModal.setAttribute("aria-hidden", "false");
    applySpecbotSettingsToForm();
  }

  function closeSpecbotSettings() {
    state.ui.isSpecbotSettingsOpen = false;
    elements.specbotSettingsModal.classList.add("hidden");
    elements.specbotSettingsModal.setAttribute("aria-hidden", "true");
  }

  function saveSpecbotSettings() {
    const rejectedClauses = getRejectedSpecbotClauses();
    const queryDepth = getSelectedSpecbotDepth();
    state.ui.specbotSettings = {
      ...state.ui.specbotSettings,
      baseUrl: elements.settingBaseUrl.value.trim(),
      configBaseUrl: elements.settingConfigBaseUrl.value.trim(),
      limit: Number(elements.settingLimit.value),
      iterations: getIterationsForDepth(queryDepth),
      nextIterationLimit: Number(elements.settingNextIterationLimit.value),
      followupMode: elements.settingFollowupMode.value,
      summary: elements.settingSummary.value,
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

  return {
    applySpecbotSettingsToForm,
    openSpecbotSettings,
    closeSpecbotSettings,
    saveSpecbotSettings,
    runSpecbotQuery,
    toggleSpecbotResultsPanel,
    buildSpecbotExclusions,
    filterSpecbotHitsByExclusions,
    pruneSpecbotResultsByCurrentExclusions,
    getRejectedSpecbotClauses,
    renderSpecbotResults,
    renderSpecbotDocumentSettings,
    renderRejectedSpecbotClauses,
    getSelectedSpecbotDocuments,
    updateSpecbotDocumentSelectionCount,
    setAllSpecbotDocuments,
    setSpecbotQueryLoading,
    applySpecbotDepthSelection,
    getSelectedSpecbotDepth,
    addRejectedSpecbotClause,
    removeRejectedSpecbotClause,
    clearRejectedSpecbotClauses,
    removeSpecbotResult,
    clearSpecbotResults,
  };
}
