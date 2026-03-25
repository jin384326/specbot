import {
  clearSpecbotResults,
  elements,
  openSpecbotSettings,
  runSpecbotQuery,
  saveSpecbotSettings,
} from "../core.js";

export function bindSpecbotFeature() {
  elements.runSpecbotQuery.addEventListener("click", () => runSpecbotQuery());
  elements.clearSpecbotResults.addEventListener("click", clearSpecbotResults);
  elements.specbotQuery.addEventListener("keydown", async (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      await runSpecbotQuery();
    }
  });
  elements.openSpecbotSettings.addEventListener("click", openSpecbotSettings);
  elements.saveSpecbotSettings.addEventListener("click", saveSpecbotSettings);
}
