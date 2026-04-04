export function createSelectionNoteController(dependencies) {
  const {
    state,
    elements,
    getSelectionNoteIndex,
    getSelectionNotesForClauseFromIndex,
    getSelectionNotesForTarget,
    getResolvedBlockIndexForReference,
    getBlockIdByIndex,
    getCurrentSelectionTargets,
    getEffectiveSelection,
    getLabelForKey,
    createHighlightEntry,
    ensureHighlightEntry,
    getAffectedClauseKeysForSelectionArtifacts,
    persistSessionState,
    rerenderLoadedNodes,
    rerenderLoadedNode,
    renderLoadedTree,
    requestSelectionSidebarRender,
    focusNode,
    setMessage,
    ensureSelectionMutationAllowed = async () => true,
    inferSourceLanguage,
    escapeHtml,
    escapeKey,
    escapeSelector,
    expandNodePath,
  } = dependencies;

  function isSelectionNoteOpen(note) {
    return note?.type === "selection"
      ? state.ui.openSelectionNoteIds.has(String(note.id || ""))
      : !note?.collapsed;
  }

  function getSelectionNoteAnchor(note) {
    const noteTargets = Array.isArray(note?.targets) ? note.targets.filter(Boolean) : [];
    if (!noteTargets.length) {
      return null;
    }
    const sortedTargets = [...noteTargets].sort((left, right) =>
      String(left.clauseKey || "").localeCompare(String(right.clauseKey || "")) ||
      getResolvedBlockIndexForReference(left.clauseKey, left.blockIndex, left.blockId)
        - getResolvedBlockIndexForReference(right.clauseKey, right.blockIndex, right.blockId) ||
      Number(left.rowIndex ?? -1) - Number(right.rowIndex ?? -1) ||
      Number(left.cellIndex ?? -1) - Number(right.cellIndex ?? -1)
    );
    return sortedTargets[0] || null;
  }

  function getHighlightEntriesForSelectionNote(note) {
    const noteTargets = Array.isArray(note?.targets) ? note.targets.filter(Boolean) : [];
    if (noteTargets.length) {
      return noteTargets
        .map((target) =>
          createHighlightEntry({
            clauseKey: target.clauseKey,
            blockId: target.blockId,
            blockIndex: target.blockIndex,
            rowIndex: target.rowIndex,
            cellIndex: target.cellIndex,
            cellId: target.cellId,
            rowText: target.rowText,
          })
        )
        .filter(Boolean);
    }
    const singleEntry = createHighlightEntry({
      clauseKey: note.clauseKey,
      blockId: note.blockId,
      blockIndex: note.blockIndex,
      rowIndex: note.rowIndex,
      cellIndex: note.cellIndex,
      cellId: note.cellId,
      rowText: note.rowText,
    });
    return singleEntry ? [singleEntry] : [];
  }

  function bindSelectionSidebarEvents() {
    if (!elements.selectionNoteOverlay) {
      return;
    }
    elements.selectionNoteOverlay.querySelectorAll("[data-action='edit-note-translation']").forEach((textarea) => {
      textarea.addEventListener("input", (event) => {
        updateNoteField(textarea.dataset.noteId || "", "translation", event.target.value);
      });
    });
    elements.selectionNoteOverlay.querySelectorAll("[data-action='delete-note']").forEach((button) => {
      button.addEventListener("click", () => {
        deleteNote(button.dataset.noteId || "");
      });
    });
    elements.selectionNoteOverlay.querySelectorAll("[data-action='toggle-selection-note-card']").forEach((button) => {
      button.addEventListener("click", () => {
        closeSelectionNoteById(button.dataset.noteId || "");
      });
    });
  }

  function renderSelectionSidebar() {
    if (!elements.selectionNotePanel) {
      return;
    }
    elements.selectionNotePanel.innerHTML = "";
    elements.selectionNotePanel.classList.add("hidden");
    elements.selectionNotePanel.setAttribute("aria-hidden", "true");
    renderSelectionNoteOverlay();
  }

  function renderSelectionNoteOverlay() {
    if (!elements.selectionNoteOverlay) {
      return;
    }
    const overlayNotes = (state.ui.notes || []).filter((note) => note.type === "selection" && isSelectionNoteOpen(note));
    if (!overlayNotes.length) {
      elements.selectionNoteOverlay.innerHTML = "";
      elements.selectionNoteOverlay.classList.add("hidden");
      elements.selectionNoteOverlay.setAttribute("aria-hidden", "true");
      return;
    }
    const cards = overlayNotes.flatMap((note) => {
      const position = getSelectionNoteOverlayPosition(note) || state.ui.selectionNoteOverlayPositions?.[String(note.id || "")] || null;
      if (!position) {
        return [];
      }
      return [`
      <article
        class="clause-note-card selection-note-floating-card"
        data-note-id="${escapeHtml(note.id)}"
        style="top:${Math.round(position.top)}px; left:${Math.round(position.left)}px; width:${Math.round(position.width)}px;"
      >
        <div class="clause-note-meta">
          <div class="clause-note-meta-main">
            <strong class="note-kind">${escapeHtml(note.clauseLabel || "선택 메모")}</strong>
          </div>
          <div class="clause-note-meta-actions">
            <button
              class="icon-button ghost note-collapse-button"
              title="접기"
              aria-label="접기"
              data-action="toggle-selection-note-card"
              data-note-id="${escapeHtml(note.id)}"
              data-clause-key="${escapeHtml(note.clauseKey || "")}"
              data-block-id="${escapeHtml(note.blockId || "")}"
              data-block-index="${Number(note.blockIndex ?? -1)}"
              data-row-index="${Number(note.rowIndex ?? -1)}"
              data-cell-index="${Number(note.cellIndex ?? -1)}"
              data-cell-id="${escapeHtml(note.cellId || "")}"
            >−</button>
            <button class="icon-button ghost note-delete-button" title="삭제" aria-label="삭제" data-action="delete-note" data-note-id="${escapeHtml(note.id)}">✕</button>
          </div>
        </div>
        <div class="clause-note-body">
          <label class="field">
            <textarea class="clause-note-textarea" data-action="edit-note-translation" data-note-id="${escapeHtml(note.id)}" rows="6" placeholder="메모를 입력하세요.">${escapeHtml(note.translation || "")}</textarea>
          </label>
        </div>
      </article>
    `];
    });
    elements.selectionNoteOverlay.innerHTML = cards.join("");
    elements.selectionNoteOverlay.classList.toggle("hidden", !cards.length);
    elements.selectionNoteOverlay.setAttribute("aria-hidden", cards.length ? "false" : "true");
    bindSelectionSidebarEvents();
  }

  function getSelectionNoteOverlayPosition(note) {
    const target = findSelectionNoteTargetElement(note) || findSelectionNoteAnchorElement(note);
    if (!(target instanceof HTMLElement)) {
      return null;
    }
    const rect = findSelectionNoteTextRect(target, note) || target.getBoundingClientRect();
    const width = Math.min(620, Math.max(320, Math.floor(window.innerWidth * 0.28)));
    const top = Math.min(window.innerHeight - 260, Math.max(16, rect.top - 8));
    const left = Math.max(16, rect.left - width - 12);
    return { top, left, width };
  }

  function findSelectionNoteTextRect(target, note) {
    const sourceText = String(note?.sourceText || "").trim();
    if (!sourceText) {
      return null;
    }
    const targetText = String(target.textContent || "");
    const startIndex = targetText.indexOf(sourceText);
    if (startIndex < 0) {
      return null;
    }
    const endIndex = startIndex + sourceText.length;
    const walker = document.createTreeWalker(target, NodeFilter.SHOW_TEXT);
    let currentOffset = 0;
    let startNode = null;
    let startNodeOffset = 0;
    let endNode = null;
    let endNodeOffset = 0;
    while (walker.nextNode()) {
      const textNode = walker.currentNode;
      const textValue = String(textNode.textContent || "");
      const nextOffset = currentOffset + textValue.length;
      if (!startNode && startIndex >= currentOffset && startIndex <= nextOffset) {
        startNode = textNode;
        startNodeOffset = Math.max(0, startIndex - currentOffset);
      }
      if (endIndex >= currentOffset && endIndex <= nextOffset) {
        endNode = textNode;
        endNodeOffset = Math.max(0, endIndex - currentOffset);
        break;
      }
      currentOffset = nextOffset;
    }
    if (!startNode || !endNode) {
      return null;
    }
    try {
      const range = document.createRange();
      range.setStart(startNode, startNodeOffset);
      range.setEnd(endNode, endNodeOffset);
      const rects = [...range.getClientRects()].filter((item) => item.width > 0 || item.height > 0);
      return rects[0] || range.getBoundingClientRect();
    } catch (_error) {
      return null;
    }
  }

  function findSelectionNoteTargetElement(note) {
    const anchor = getSelectionNoteAnchor(note);
    const clauseKey = String(anchor?.clauseKey || note?.clauseKey || "").trim();
    const blockId = String(anchor?.blockId || note?.blockId || "").trim();
    const cellId = String(anchor?.cellId || note?.cellId || "").trim();
    const rowIndex = Number(anchor?.rowIndex ?? note?.rowIndex ?? -1);
    if (!clauseKey || !blockId) {
      return null;
    }
    const host = document.querySelector(
      `.clause-editor-host[data-editor-node-key="${escapeSelector(clauseKey)}"]`
    );
    if (!(host instanceof HTMLElement)) {
      return null;
    }
    if (cellId) {
      return host.querySelector(
        `[data-editor-block-id="${escapeSelector(blockId)}"] [data-editor-cell-id="${escapeSelector(cellId)}"]`
      );
    }
    const blockElement = host.querySelector(`[data-editor-block-id="${escapeSelector(blockId)}"]`);
    if (!(blockElement instanceof HTMLElement)) {
      return null;
    }
    if (rowIndex >= 0 && blockElement.tagName.toLowerCase() === "table") {
      const row = blockElement.querySelectorAll("tr")[rowIndex];
      if (row instanceof HTMLElement) {
        return row;
      }
    }
    return blockElement;
  }

  function findSelectionNoteAnchorElement(note) {
    const anchor = getSelectionNoteAnchor(note);
    const clauseKey = String(anchor?.clauseKey || note?.clauseKey || "").trim();
    const blockId = String(anchor?.blockId || note?.blockId || "").trim();
    const cellId = String(anchor?.cellId || note?.cellId || "").trim();
    const rowIndex = Number(anchor?.rowIndex ?? note?.rowIndex ?? -1);
    const blockIndex = getResolvedBlockIndexForReference(clauseKey, anchor?.blockIndex ?? note?.blockIndex, blockId);
    const selector = [
      `[data-action="toggle-selection-notes"]`,
      `[data-clause-key="${escapeSelector(clauseKey)}"]`,
      `[data-block-index="${blockIndex}"]`,
      `[data-row-index="${rowIndex}"]`,
      `[data-block-id="${escapeSelector(blockId)}"]`,
      cellId ? `[data-cell-id="${escapeSelector(cellId)}"]` : "",
    ].join("");
    return document.querySelector(selector);
  }

  function syncEditorNoteRailPositions() {
    window.requestAnimationFrame(() => {
      document.querySelectorAll(".editor-section-with-rail").forEach((section) => {
        const rail = section.querySelector(".editor-note-rail");
        const host = section.querySelector(".clause-editor-host");
        if (!(rail instanceof HTMLElement) || !(host instanceof HTMLElement)) {
          return;
        }
        const hostRect = host.getBoundingClientRect();
        rail.style.minHeight = `${Math.ceil(host.scrollHeight || hostRect.height || 0)}px`;
        rail.querySelectorAll(".editor-note-anchor").forEach((anchor) => {
          const button = anchor.querySelector("[data-action='toggle-selection-notes']");
          if (!(anchor instanceof HTMLElement) || !(button instanceof HTMLElement)) {
            return;
          }
          const pseudoNote = {
            clauseKey: button.dataset.clauseKey || "",
            blockId: button.dataset.blockId || "",
            blockIndex: Number(button.dataset.blockIndex || -1),
            rowIndex: Number(button.dataset.rowIndex || -1),
            cellIndex: Number(button.dataset.cellIndex || -1),
            cellId: button.dataset.cellId || "",
          };
          const target = findSelectionNoteTargetElement(pseudoNote);
          if (!(target instanceof HTMLElement)) {
            return;
          }
          const targetRect = target.getBoundingClientRect();
          anchor.style.top = `${Math.max(0, Math.round(targetRect.top - hostRect.top - 2))}px`;
        });
      });
    });
  }

  function upsertNote(note) {
    const existingIndex = (state.ui.notes || []).findIndex((item) => item.id === note.id);
    if (existingIndex >= 0) {
      state.ui.notes = state.ui.notes.map((item, index) => (index === existingIndex ? { ...item, ...note } : item));
    } else {
      state.ui.notes = [note, ...(state.ui.notes || [])];
    }
    if (note.type === "selection") {
      const nextOpen = new Set(state.ui.openSelectionNoteIds || []);
      nextOpen.add(String(note.id || ""));
      state.ui.openSelectionNoteIds = nextOpen;
      getHighlightEntriesForSelectionNote(note).forEach((entry) => {
        ensureHighlightEntry(entry);
      });
    }
    if (note.type === "clause" && note.clauseKey) {
      expandNodePath(note.clauseKey);
    }
    persistSessionState();
    const affectedClauseKeys = getAffectedClauseKeysForSelectionArtifacts([note]);
    if (note.type === "selection" && affectedClauseKeys.length) {
      rerenderLoadedNodes(affectedClauseKeys);
    } else if (note.type === "clause" && note.clauseKey) {
      rerenderLoadedNode(note.clauseKey);
    } else {
      renderLoadedTree();
    }
  }

  function updateNoteField(noteId, field, value) {
    state.ui.notes = (state.ui.notes || []).map((note) => (note.id === noteId ? { ...note, [field]: value } : note));
    persistSessionState();
  }

  function getSelectionNoteOverlayPositionFromTrigger(triggerElement) {
    if (!(triggerElement instanceof HTMLElement)) {
      return null;
    }
    const rect = triggerElement.getBoundingClientRect();
    const width = Math.min(620, Math.max(320, Math.floor(window.innerWidth * 0.28)));
    const top = Math.min(window.innerHeight - 260, Math.max(16, rect.top - 8));
    const left = Math.max(16, rect.left - width - 12);
    return { top, left, width };
  }

  function toggleSelectionNotes(clauseKey, blockIndex, rowIndex = -1, cellIndex = null, blockId = getBlockIdByIndex(clauseKey, blockIndex), cellId = "") {
    const notes = getSelectionNotesForTarget(clauseKey, blockIndex, rowIndex, cellIndex, blockId, cellId);
    toggleSelectionNotesByIds(
      notes.map((note) => String(note.id || "")).filter(Boolean),
      { clauseKey, blockIndex, rowIndex, cellIndex: cellIndex === null ? -1 : cellIndex, blockId, cellId }
    );
  }

  function toggleSelectionNotesByIds(noteIds, anchor = {}, triggerElement = null) {
    const normalizedIds = [...new Set((noteIds || []).map((item) => String(item || "").trim()).filter(Boolean))];
    if (!normalizedIds.length) {
      return;
    }
    let notes = (state.ui.notes || []).filter((note) => normalizedIds.includes(String(note.id || "")));
    if (!notes.length && anchor?.clauseKey) {
      notes = getSelectionNotesForTarget(
        String(anchor.clauseKey || ""),
        Number(anchor.blockIndex ?? -1),
        Number(anchor.rowIndex ?? -1),
        anchor.cellIndex === null || anchor.cellIndex === undefined ? null : Number(anchor.cellIndex),
        String(anchor.blockId || ""),
        String(anchor.cellId || "")
      );
    }
    if (!notes.length) {
      return;
    }
    const effectiveIds = [...new Set(notes.map((note) => String(note.id || "")).filter(Boolean))];
    const openIds = new Set(state.ui.openSelectionNoteIds || []);
    const shouldCollapse = notes.some((note) => isSelectionNoteOpen(note));
    const normalizedBlockId = String(anchor.blockId || "").trim() || getBlockIdByIndex(anchor.clauseKey || "", Number(anchor.blockIndex || -1)) || "";
    const normalizedCellId = String(anchor.cellId || "").trim();
    if (!shouldCollapse) {
      const nextPositions = { ...(state.ui.selectionNoteOverlayPositions || {}) };
      const resolvedPosition = getSelectionNoteOverlayPosition({
        clauseKey: String(anchor.clauseKey || notes[0]?.clauseKey || ""),
        blockId: normalizedBlockId || String(notes[0]?.blockId || ""),
        blockIndex: Number(anchor.blockIndex ?? notes[0]?.blockIndex ?? -1),
        rowIndex: Number(anchor.rowIndex ?? notes[0]?.rowIndex ?? -1),
        cellIndex: Number(anchor.cellIndex ?? notes[0]?.cellIndex ?? -1),
        cellId: normalizedCellId || String(notes[0]?.cellId || ""),
        sourceText: String(notes[0]?.sourceText || ""),
      }) || getSelectionNoteOverlayPositionFromTrigger(triggerElement);
      effectiveIds.forEach((id) => {
        if (resolvedPosition) {
          nextPositions[id] = resolvedPosition;
        }
      });
      state.ui.selectionNoteOverlayPositions = nextPositions;
      state.ui.notes = (state.ui.notes || []).map((note) =>
        effectiveIds.includes(String(note.id || ""))
          ? {
              ...note,
              clauseKey: String(anchor.clauseKey || note.clauseKey || ""),
              blockIndex: Number(anchor.blockIndex ?? note.blockIndex ?? -1),
              blockId: normalizedBlockId || String(note.blockId || ""),
              rowIndex: Number(anchor.rowIndex ?? note.rowIndex ?? -1),
              cellIndex: Number(anchor.cellIndex ?? note.cellIndex ?? -1),
              cellId: normalizedCellId || String(note.cellId || ""),
              rowText: String(anchor.rowText || note.rowText || ""),
            }
          : note
      );
    }
    effectiveIds.forEach((id) => {
      if (shouldCollapse) {
        openIds.delete(id);
      } else {
        openIds.add(id);
      }
    });
    state.ui.openSelectionNoteIds = openIds;
    persistSessionState();
    requestSelectionSidebarRender();
    syncSelectionNoteToggleButtons();
  }

  function collapseAllSelectionNotes() {
    state.ui.openSelectionNoteIds = new Set();
    persistSessionState();
    requestSelectionSidebarRender();
    syncSelectionNoteToggleButtons();
  }

  function closeSelectionNoteById(noteId) {
    const normalizedNoteId = String(noteId || "").trim();
    if (!normalizedNoteId) {
      return;
    }
    const openIds = new Set(state.ui.openSelectionNoteIds || []);
    openIds.delete(normalizedNoteId);
    state.ui.openSelectionNoteIds = openIds;
    persistSessionState();
    requestSelectionSidebarRender();
    syncSelectionNoteToggleButtons();
  }

  function syncSelectionNoteToggleButtons() {
    document.querySelectorAll("[data-action='toggle-selection-notes']").forEach((button) => {
      const noteIds = String(button.dataset.noteIds || "").split(",").map((item) => item.trim()).filter(Boolean);
      const expanded = noteIds.some((id) => state.ui.openSelectionNoteIds.has(id));
      button.classList.toggle("expanded", expanded);
    });
  }

  function toggleSelectionNoteCard(noteId) {
    const normalizedNoteId = String(noteId || "").trim();
    if (!normalizedNoteId) {
      return;
    }
    let openedNote = null;
    const openIds = new Set(state.ui.openSelectionNoteIds || []);
    if (openIds.has(normalizedNoteId)) {
      openIds.delete(normalizedNoteId);
    } else {
      openIds.add(normalizedNoteId);
      openedNote = (state.ui.notes || []).find((note) => note.id === normalizedNoteId) || null;
    }
    state.ui.openSelectionNoteIds = openIds;
    persistSessionState();
    renderLoadedTree();
    if (openedNote) {
      revealSelectionNoteTarget(openedNote);
    }
  }

  function revealSelectionNoteTarget(note) {
    const noteTargets = Array.isArray(note?.targets) && note.targets.length
      ? note.targets
      : [{
          clauseKey: note?.clauseKey || "",
          blockId: note?.blockId || "",
          cellId: note?.cellId || "",
        }];
    const primaryTarget = noteTargets.find((target) => String(target?.clauseKey || "").trim()) || null;
    if (!primaryTarget?.clauseKey) {
      return;
    }
    focusNode(primaryTarget.clauseKey);
    window.setTimeout(() => {
      const targets = noteTargets.flatMap((target) => {
        const clauseKey = String(target?.clauseKey || "").trim();
        if (!clauseKey) {
          return [];
        }
        const nodeElement = document.getElementById(`node-${escapeKey(clauseKey)}`);
        if (!(nodeElement instanceof HTMLElement)) {
          return [];
        }
        const cellId = String(target?.cellId || "").trim();
        const blockId = String(target?.blockId || "").trim();
        let element = null;
        if (cellId) {
          element = nodeElement.querySelector(`[data-editor-cell-id="${escapeSelector(cellId)}"]`);
        }
        if (!element && blockId) {
          element = nodeElement.querySelector(`[data-editor-block-id="${escapeSelector(blockId)}"]`);
        }
        return element ? [element] : [];
      });
      if (!targets.length) {
        return;
      }
      const uniqueTargets = [...new Set(targets)];
      uniqueTargets[0].scrollIntoView({ behavior: "smooth", block: "center", inline: "nearest" });
      uniqueTargets.forEach((target) => target.classList.add("note-target-reveal"));
      window.setTimeout(() => {
        uniqueTargets.forEach((target) => target.classList.remove("note-target-reveal"));
      }, 1800);
    }, 80);
  }

  function pruneHighlightForSelectionNote(note) {
    const linkedEntries = getHighlightEntriesForSelectionNote(note);
    if (!linkedEntries.length) {
      return;
    }
    const siblingHighlightIds = new Set(
      (state.ui.notes || [])
        .filter((item) => item.type === "selection" && item.id !== note.id)
        .flatMap((item) => getHighlightEntriesForSelectionNote(item).map((entry) => entry.id))
    );
    const removableIds = new Set(
      linkedEntries
        .map((entry) => entry.id)
        .filter((entryId) => !siblingHighlightIds.has(entryId))
    );
    if (!removableIds.size) {
      return;
    }
    state.ui.highlights = (state.ui.highlights || []).filter((item) => !removableIds.has(item.id));
  }

  function deleteNote(noteId) {
    const targetNote = (state.ui.notes || []).find((note) => note.id === noteId) || null;
    state.ui.notes = (state.ui.notes || []).filter((note) => note.id !== noteId);
    const openIds = new Set(state.ui.openSelectionNoteIds || []);
    openIds.delete(String(noteId || ""));
    state.ui.openSelectionNoteIds = openIds;
    const nextPositions = { ...(state.ui.selectionNoteOverlayPositions || {}) };
    delete nextPositions[String(noteId || "")];
    state.ui.selectionNoteOverlayPositions = nextPositions;
    if (targetNote?.type === "selection") {
      pruneHighlightForSelectionNote(targetNote);
    }
    if (state.ui.clauseNoteModalKey) {
      const remaining = (state.ui.notes || []).filter(
        (note) => note.clauseKey === state.ui.clauseNoteModalKey && note.type === "clause" && note.id !== noteId
      );
      if (!remaining.length) {
        state.ui.clauseNoteModalKey = "";
        elements.clauseNoteModal.classList.add("hidden");
        elements.clauseNoteModal.setAttribute("aria-hidden", "true");
      }
    }
    persistSessionState();
    const affectedClauseKeys = targetNote ? getAffectedClauseKeysForSelectionArtifacts([targetNote]) : [];
    if (targetNote?.type === "selection" && affectedClauseKeys.length) {
      rerenderLoadedNodes(affectedClauseKeys);
    } else if (targetNote?.clauseKey) {
      rerenderLoadedNode(targetNote.clauseKey);
    } else {
      renderLoadedTree();
    }
  }

  async function addManualSelectionNote() {
    const selectionTargets = getCurrentSelectionTargets();
    const selection = getEffectiveSelection();
    if (!selectionTargets.length) {
      setMessage("메모를 추가할 문단이나 표 셀을 먼저 선택하세요.", true);
      return;
    }
    if (!(await ensureSelectionMutationAllowed("선택 메모를 추가"))) {
      return;
    }
    const anchorTarget = selectionTargets[0];
    const sourceText = String(
      selection?.hasSelection && selection?.text
        ? selection.text
        : anchorTarget.rowText || ""
    ).trim();
    upsertNote({
      id: `manual-note:${Date.now()}:${Math.random().toString(36).slice(2, 8)}`,
      type: "selection",
      clauseKey: anchorTarget.clauseKey,
      blockId: anchorTarget.blockId,
      blockIndex: anchorTarget.blockIndex,
      rowIndex: anchorTarget.rowIndex,
      cellIndex: anchorTarget.cellIndex,
      cellId: anchorTarget.cellId,
      rowText: anchorTarget.rowText,
      targets: selectionTargets,
      clauseLabel: anchorTarget.clauseLabel || getLabelForKey(anchorTarget.clauseKey),
      sourceText,
      translation: "",
      sourceLanguage: inferSourceLanguage(sourceText),
      targetLanguage: "memo",
      collapsed: false,
    });
  }

  function clearSelectionNoteUiState() {
    state.ui.openSelectionNoteIds = new Set();
    state.ui.selectionNoteOverlayPositions = {};
    state.ui.selectionSnapshot = null;
    if (elements.selectionNoteOverlay) {
      elements.selectionNoteOverlay.innerHTML = "";
      elements.selectionNoteOverlay.classList.add("hidden");
      elements.selectionNoteOverlay.setAttribute("aria-hidden", "true");
    }
    syncSelectionNoteToggleButtons();
  }

  function renderEditorNoteRail(node) {
    const selectionNotes = getSelectionNotesForClauseFromIndex(getSelectionNoteIndex(), node.key)
      .sort((left, right) =>
        getResolvedBlockIndexForReference(left.clauseKey, left.blockIndex, left.blockId) - getResolvedBlockIndexForReference(right.clauseKey, right.blockIndex, right.blockId) ||
        Number(left.rowIndex ?? -1) - Number(right.rowIndex ?? -1) ||
        Number(left.cellIndex ?? -1) - Number(right.cellIndex ?? -1)
      );
    if (!selectionNotes.length) {
      return "";
    }
    const seen = new Set();
    const anchors = selectionNotes.flatMap((note) => {
      const anchor = getSelectionNoteAnchor(note) || note;
      const blockIndex = getResolvedBlockIndexForReference(anchor.clauseKey || note.clauseKey, anchor.blockIndex, anchor.blockId);
      const blockId = String(anchor.blockId || note.blockId || getBlockIdByIndex(note.clauseKey, blockIndex) || "");
      const rowIndex = Number(anchor.rowIndex ?? -1);
      const cellIndex = Number(anchor.cellIndex ?? -1);
      const cellId = String(anchor.cellId || "").trim();
      const anchorKey = [note.clauseKey, blockId, rowIndex, cellId || cellIndex].join(":");
      if (seen.has(anchorKey)) {
        return [];
      }
      seen.add(anchorKey);
      return [{
        clauseKey: note.clauseKey,
        blockIndex,
        blockId,
        rowIndex,
        cellIndex,
        cellId,
        label:
          rowIndex >= 0
            ? cellIndex >= 0
              ? `R${rowIndex + 1} C${cellIndex + 1}`
              : `R${rowIndex + 1}`
            : `P${blockIndex + 1}`,
      }];
    });
    return anchors;
  }

  return {
    isSelectionNoteOpen,
    getHighlightEntriesForSelectionNote,
    getSelectionNoteAnchor,
    findSelectionNoteTargetElement,
    renderSelectionSidebar,
    syncEditorNoteRailPositions,
    upsertNote,
    updateNoteField,
    toggleSelectionNotes,
    toggleSelectionNotesByIds,
    collapseAllSelectionNotes,
    closeSelectionNoteById,
    syncSelectionNoteToggleButtons,
    toggleSelectionNoteCard,
    revealSelectionNoteTarget,
    deleteNote,
    addManualSelectionNote,
    clearSelectionNoteUiState,
    renderEditorNoteRail,
  };
}
