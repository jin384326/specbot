import { elements, exportDocx, exportMarkdown, exportMarkdownPackage, openExportModal } from "../core.js";
export { getExportRequestConfig, resolveDownloadFileName } from "../utils/export.js";

export function bindExportFeature() {
  elements.exportButton.addEventListener("click", openExportModal);
  if (elements.exportModalDocxButton) {
    elements.exportModalDocxButton.addEventListener("click", exportDocx);
  }
  if (elements.exportModalMarkdownButton) {
    elements.exportModalMarkdownButton.addEventListener("click", exportMarkdown);
  }
  if (elements.exportModalMarkdownPackageButton) {
    elements.exportModalMarkdownPackageButton.addEventListener("click", exportMarkdownPackage);
  }
}
