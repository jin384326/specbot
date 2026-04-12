export function resolveDownloadFileName(contentDisposition, fallbackName) {
  const disposition = String(contentDisposition || "");
  const utf8Match = disposition.match(/filename\*=UTF-8''([^;]+)/i);
  const asciiMatch = disposition.match(/filename="([^"]+)"/i);
  if (utf8Match?.[1]) {
    try {
      return decodeURIComponent(utf8Match[1]);
    } catch (_error) {
      return fallbackName;
    }
  }
  return asciiMatch?.[1] || fallbackName;
}

export function getExportRequestConfig(format) {
  if (format === "docx") {
    return {
      busyLabel: "DOCX export 실행 중입니다.",
      endpoint: "/api/clause-browser/exports/docx/download",
      accept: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      fallbackExtension: "docx",
    };
  }
  if (format === "markdown") {
    return {
      busyLabel: "Markdown export 실행 중입니다.",
      endpoint: "/api/clause-browser/exports/markdown/download",
      accept: "text/markdown",
      fallbackExtension: "md",
    };
  }
  if (format === "markdown-package") {
    return {
      busyLabel: "Markdown + assets export 실행 중입니다.",
      endpoint: "/api/clause-browser/exports/markdown-package/download",
      accept: "application/zip",
      fallbackExtension: "zip",
    };
  }
  throw new Error(`Unsupported export format: ${format}`);
}
