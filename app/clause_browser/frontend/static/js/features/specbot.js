import {
  clearRejectedSpecbotClauses,
  clearSpecbotResults,
  elements,
  openSpecbotSettings,
  runSpecbotQuery,
  saveSpecbotSettings,
  setAllSpecbotDocuments,
} from "../core.js";

export function bindSpecbotFeature() {
  elements.clearSpecbotResults.addEventListener("click", clearSpecbotResults);
  elements.specbotQuery.addEventListener("keydown", async (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      await runSpecbotQuery();
    }
  });
  elements.openSpecbotSettings.addEventListener("click", openSpecbotSettings);
  elements.settingSelectAllDocuments.addEventListener("click", () => setAllSpecbotDocuments(true));
  elements.settingClearAllDocuments.addEventListener("click", () => setAllSpecbotDocuments(false));
  elements.settingClearRejectedClauses.addEventListener("click", clearRejectedSpecbotClauses);
  elements.saveSpecbotSettings.addEventListener("click", saveSpecbotSettings);
}
