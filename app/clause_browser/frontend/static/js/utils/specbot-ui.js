export function buildSpecbotResultsHtml(results, escapeHtml) {
  if (!results.length) {
    return '<div class="muted">상단 Query로 SpecBot을 실행하면 결과가 여기에 표시됩니다.</div>';
  }
  return results
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
}

export function buildSpecbotDocumentSettingsHtml(docs, selectedSpecs, escapeHtml) {
  if (!docs.length) {
    return '<div class="muted">선택 가능한 문서가 없습니다.</div>';
  }
  return docs
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
}

export function buildRejectedSpecbotClausesHtml(rejectedClauses, escapeHtml) {
  if (!rejectedClauses.length) {
    return '<div class="muted">거절로 제외된 절이 없습니다.</div>';
  }
  return rejectedClauses
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
}

export function getSpecbotDocumentSelectionCount(selectedCount, totalCount) {
  return `${selectedCount} / ${totalCount} selected`;
}

export function getSpecbotQueryLoadingLabel(queryStatus) {
  const normalizedStatus = String(queryStatus || "").trim();
  if (normalizedStatus === "queued") {
    return "대기 중";
  }
  if (normalizedStatus === "started") {
    return "실행 중";
  }
  return "수행 중";
}

export function normalizeSpecbotDepth(depth) {
  return depth === "short" || depth === "long" ? depth : "medium";
}
