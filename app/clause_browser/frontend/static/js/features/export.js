import { elements, exportDocx } from "../core.js";

export function bindExportFeature() {
  elements.exportButton.addEventListener("click", exportDocx);
}
