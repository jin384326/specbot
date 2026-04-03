function createRenderBatcher(scheduleFrame = (callback) => window.requestAnimationFrame(callback)) {
  const pendingJobs = new Map();

  return {
    schedule(key, job) {
      const normalizedKey = String(key || "").trim();
      if (!normalizedKey || typeof job !== "function") {
        return;
      }
      pendingJobs.set(normalizedKey, job);
      if (pendingJobs.get(`${normalizedKey}:scheduled`)) {
        return;
      }
      pendingJobs.set(`${normalizedKey}:scheduled`, true);
      scheduleFrame(() => {
        const nextJob = pendingJobs.get(normalizedKey);
        pendingJobs.delete(normalizedKey);
        pendingJobs.delete(`${normalizedKey}:scheduled`);
        nextJob?.();
      });
    },
  };
}

export {
  createRenderBatcher,
};
