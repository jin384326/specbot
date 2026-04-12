function toPositiveInteger(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric) || numeric <= 0) {
    return null;
  }
  return Math.round(numeric);
}

export function getImageDisplayDimensions(source) {
  const width = toPositiveInteger(source?.displayWidthPx);
  const height = toPositiveInteger(source?.displayHeightPx);
  return {
    width,
    height,
  };
}

export function buildImageDisplayAttributes(source) {
  const { width, height } = getImageDisplayDimensions(source);
  return [
    width ? ` width="${width}" data-display-width-px="${width}"` : "",
    height ? ` height="${height}" data-display-height-px="${height}"` : "",
  ].join("");
}

export function extractImageDisplayDimensionsFromElement(element) {
  if (!element) {
    return {};
  }
  const width = toPositiveInteger(element.dataset?.displayWidthPx || element.getAttribute?.("data-display-width-px") || element.getAttribute?.("width"));
  const height = toPositiveInteger(element.dataset?.displayHeightPx || element.getAttribute?.("data-display-height-px") || element.getAttribute?.("height"));
  return {
    ...(width ? { displayWidthPx: width } : {}),
    ...(height ? { displayHeightPx: height } : {}),
  };
}

export function shouldAllowNativeImageContextMenu(target) {
  const isElementLike = (value) => Boolean(value && typeof value === "object" && typeof value.tagName === "string");
  const hasHTMLElement = typeof HTMLElement !== "undefined";
  const element =
    hasHTMLElement && target instanceof HTMLElement
      ? target
      : hasHTMLElement && target?.parentElement instanceof HTMLElement
        ? target.parentElement
        : isElementLike(target)
          ? target
          : isElementLike(target?.parentElement)
            ? target.parentElement
        : null;
  if (!element) {
    return false;
  }
  if (element.tagName?.toLowerCase?.() === "img") {
    return true;
  }
  if (typeof element.closest === "function" && element.closest(".docx-figure[data-block-type='image']")) {
    return true;
  }
  return false;
}
