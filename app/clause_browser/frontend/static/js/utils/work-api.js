export function resolveWorkApiUrl(baseUrl, url) {
  const normalizedBaseUrl = String(baseUrl || "").trim();
  if (!normalizedBaseUrl) {
    throw new Error("Query API URL is not configured.");
  }
  if (url === "/api/clause-browser/specbot/query") {
    return `${normalizedBaseUrl}/query`;
  }
  if (url === "/api/clause-browser/llm-actions") {
    return `${normalizedBaseUrl}/llm-actions`;
  }
  if (url === "/api/clause-browser/llm-actions-stream") {
    return `${normalizedBaseUrl}/llm-actions-stream`;
  }
  return url;
}

export function formatErrorMessage(value) {
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

export function mergeSpecbotHits(existingHits, incomingHits, { exclusions, filterHitsByExclusions, compareHits }) {
  const merged = new Map(((existingHits || []).map((item) => [`${item.specNo}:${item.clauseId}`, item])));
  for (const hit of filterHitsByExclusions(incomingHits || [], exclusions)) {
    const key = `${hit.specNo}:${hit.clauseId}`;
    if (!merged.has(key)) {
      merged.set(key, hit);
    }
  }
  return [...merged.values()].sort(compareHits);
}

export async function parseResponse(response) {
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return await response.json();
  }
  const text = await response.text();
  return { detail: text || `HTTP ${response.status}` };
}

export function normalizeRequestError(error) {
  if (error?.name === "AbortError") {
    return new Error("__REQUEST_ABORTED__");
  }
  return error;
}

export function isAbortedRequestError(error) {
  return error instanceof Error && error.message === "__REQUEST_ABORTED__";
}

export function createWorkApi(dependencies) {
  const {
    state,
    persistSessionState,
    renderSpecbotResults,
    renderTranslationStatus,
    setMessage,
    setSpecbotQueryLoading,
    buildSpecbotExclusions,
    filterSpecbotHitsByExclusions,
    compareSpecbotHits,
    workSlotLimit,
    workSlotTtlMs,
    workStateKey,
    workLockKey,
    workTabId,
    workLockTtlMs,
    fetchImpl = fetch,
    textDecoderClass = TextDecoder,
  } = dependencies;

  const activeRequestControllers = new Set();
  const activeLocalWorkSlots = new Set();

  function getQueryApiUrl() {
    return String(state.config?.queryApiUrl || "").trim();
  }

  function registerRequestController() {
    const controller = new AbortController();
    activeRequestControllers.add(controller);
    return {
      signal: controller.signal,
      release: () => activeRequestControllers.delete(controller),
    };
  }

  async function wait(ms) {
    return await new Promise((resolve) => window.setTimeout(resolve, ms));
  }

  function readLocalWorkSlots() {
    const raw = localStorage.getItem(workStateKey);
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
    return entries.filter((entry) => entry && entry.id && Number(entry.createdAt) > now - workSlotTtlMs);
  }

  function writeLocalWorkSlots(entries) {
    localStorage.setItem(workStateKey, JSON.stringify(entries));
  }

  async function withLocalWorkLock(fn) {
    const lockId = `${workTabId}:${Date.now()}:${Math.random().toString(36).slice(2, 8)}`;
    while (true) {
      const now = Date.now();
      const raw = localStorage.getItem(workLockKey);
      if (raw) {
        try {
          const lock = JSON.parse(raw);
          if (lock && Number(lock.expiresAt) > now && lock.id !== lockId) {
            await wait(25);
            continue;
          }
        } catch (_error) {
          // Ignore malformed lock state and acquire a fresh lock.
        }
      }
      localStorage.setItem(
        workLockKey,
        JSON.stringify({ id: lockId, expiresAt: now + workLockTtlMs })
      );
      try {
        const verify = JSON.parse(localStorage.getItem(workLockKey) || "{}");
        if (verify.id !== lockId) {
          await wait(25);
          continue;
        }
        return fn();
      } finally {
        const current = localStorage.getItem(workLockKey);
        try {
          const parsed = current ? JSON.parse(current) : {};
          if (parsed.id === lockId) {
            localStorage.removeItem(workLockKey);
          }
        } catch (_error) {
          localStorage.removeItem(workLockKey);
        }
      }
    }
  }

  async function reserveLocalWorkSlot() {
    return await withLocalWorkLock(() => {
      const entries = readLocalWorkSlots();
      if (entries.length >= workSlotLimit) {
        throw new Error("현재 브라우저 작업 대기열이 가득 찼습니다. 잠시 후 다시 시도하세요.");
      }
      const slotId = `${workTabId}:${Date.now()}:${Math.random().toString(36).slice(2, 8)}`;
      entries.push({ id: slotId, tabId: workTabId, createdAt: Date.now() });
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

  function abortActiveRequests() {
    activeRequestControllers.forEach((controller) => controller.abort());
    activeRequestControllers.clear();
    const slotIds = [...activeLocalWorkSlots];
    activeLocalWorkSlots.clear();
    slotIds.forEach((slotId) => {
      void releaseLocalWorkSlot(slotId);
    });
  }

  async function apiGet(url) {
    const { signal, release } = registerRequestController();
    let response;
    try {
      response = await fetchImpl(url, { signal });
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
      response = await fetchImpl(url, {
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
    const targetUrl = resolveWorkApiUrl(getQueryApiUrl(), url);
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
      state.ui.specbotResults = mergeSpecbotHits(state.ui.specbotResults, [event.hit], {
        exclusions,
        filterHitsByExclusions: filterSpecbotHitsByExclusions,
        compareHits: compareSpecbotHits,
      });
      persistSessionState();
      renderSpecbotResults();
      state.ui.specbotQueryStatus = "started";
      setSpecbotQueryLoading(true);
      setMessage(`SpecBot query 진행 중: ${event.hit?.specNo || ""} / ${event.hit?.clauseId || ""}`, false);
      return {
        ...finalPayload,
        hits: mergeSpecbotHits(finalPayload.hits || [], [event.hit], {
          exclusions,
          filterHitsByExclusions: filterSpecbotHitsByExclusions,
          compareHits: compareSpecbotHits,
        }),
      };
    }
    if (event.type === "hits") {
      const exclusions = buildSpecbotExclusions();
      state.ui.specbotResults = mergeSpecbotHits(state.ui.specbotResults, event.hits || [], {
        exclusions,
        filterHitsByExclusions: filterSpecbotHitsByExclusions,
        compareHits: compareSpecbotHits,
      });
      persistSessionState();
      renderSpecbotResults();
      state.ui.specbotQueryStatus = "started";
      setSpecbotQueryLoading(true);
      setMessage(`SpecBot query 진행 중: iteration ${event.iteration}`, false);
      return {
        ...finalPayload,
        hits: mergeSpecbotHits(finalPayload.hits || [], event.hits || [], {
          exclusions,
          filterHitsByExclusions: filterSpecbotHitsByExclusions,
          compareHits: compareSpecbotHits,
        }),
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

  async function streamSpecbotQuery(body) {
    const targetUrl = resolveWorkApiUrl(getQueryApiUrl(), "/api/clause-browser/specbot/query").replace(/\/query$/, "/query-stream");
    const slotId = await reserveLocalWorkSlot();
    activeLocalWorkSlots.add(slotId);
    const { signal, release } = registerRequestController();
    let response;
    try {
      response = await fetchImpl(targetUrl, {
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

    const decoder = new textDecoderClass();
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
    const response = await fetchImpl(resolveWorkApiUrl(getQueryApiUrl(), `${url}-stream`), {
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

    const decoder = new textDecoderClass();
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

  return {
    apiGet,
    apiPost,
    apiPostWork,
    streamSpecbotQuery,
    streamLlmAction,
    abortActiveRequests,
  };
}
