import test from "node:test";
import assert from "node:assert/strict";

import { getExportRequestConfig, resolveDownloadFileName } from "../static/js/utils/export.js";

test("resolveDownloadFileName prefers UTF-8 content disposition names", () => {
  const fileName = resolveDownloadFileName(
    "attachment; filename=\"Session_Export.docx\"; filename*=UTF-8''%EC%83%88_%EA%B2%8C%EC%8B%9C%EA%B8%80.md",
    "fallback.md"
  );

  assert.equal(fileName, "새_게시글.md");
});

test("resolveDownloadFileName falls back to ascii and default names", () => {
  assert.equal(resolveDownloadFileName('attachment; filename="Session_Export.md"', "fallback.md"), "Session_Export.md");
  assert.equal(resolveDownloadFileName("", "fallback.md"), "fallback.md");
});

test("getExportRequestConfig returns stable export endpoint metadata", () => {
  assert.deepEqual(getExportRequestConfig("docx"), {
    busyLabel: "DOCX export 실행 중입니다.",
    endpoint: "/api/clause-browser/exports/docx/download",
    accept: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    fallbackExtension: "docx",
  });
  assert.deepEqual(getExportRequestConfig("markdown"), {
    busyLabel: "Markdown export 실행 중입니다.",
    endpoint: "/api/clause-browser/exports/markdown/download",
    accept: "text/markdown",
    fallbackExtension: "md",
  });
  assert.deepEqual(getExportRequestConfig("markdown-package"), {
    busyLabel: "Markdown + assets export 실행 중입니다.",
    endpoint: "/api/clause-browser/exports/markdown-package/download",
    accept: "application/zip",
    fallbackExtension: "zip",
  });
});

test("export busy labels remain explicit and stable", () => {
  const docxLabel = getExportRequestConfig("docx").busyLabel;
  const markdownLabel = getExportRequestConfig("markdown").busyLabel;
  const packageLabel = getExportRequestConfig("markdown-package").busyLabel;

  assert.equal(docxLabel, "DOCX export 실행 중입니다.");
  assert.equal(markdownLabel, "Markdown export 실행 중입니다.");
  assert.equal(packageLabel, "Markdown + assets export 실행 중입니다.");
});
