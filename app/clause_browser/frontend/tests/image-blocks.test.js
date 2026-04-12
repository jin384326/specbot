import test from "node:test";
import assert from "node:assert/strict";

import {
  buildImageDisplayAttributes,
  extractImageDisplayDimensionsFromElement,
  shouldAllowNativeImageContextMenu,
} from "../static/js/utils/image-blocks.js";

test("image block utilities build and recover display dimensions", () => {
  const attributes = buildImageDisplayAttributes({ displayWidthPx: 384, displayHeightPx: 256 });

  assert.match(attributes, /width="384"/);
  assert.match(attributes, /height="256"/);

  const dimensions = extractImageDisplayDimensionsFromElement({
    dataset: {
      displayWidthPx: "384",
      displayHeightPx: "256",
    },
    getAttribute(name) {
      return this.dataset[name.replace(/-([a-z])/g, (_match, char) => char.toUpperCase())] || null;
    },
  });

  assert.deepEqual(dimensions, { displayWidthPx: 384, displayHeightPx: 256 });
});

test("image context menu helper allows native menu on images and image figures only", () => {
  const imageTarget = {
    tagName: "IMG",
    closest() {
      return null;
    },
  };
  const figureTarget = {
    tagName: "FIGCAPTION",
    closest(selector) {
      return selector === ".docx-figure[data-block-type='image']" ? {} : null;
    },
  };
  const textTarget = {
    tagName: "P",
    closest() {
      return null;
    },
  };

  assert.equal(shouldAllowNativeImageContextMenu(imageTarget), true);
  assert.equal(shouldAllowNativeImageContextMenu(figureTarget), true);
  assert.equal(shouldAllowNativeImageContextMenu(textTarget), false);
});
