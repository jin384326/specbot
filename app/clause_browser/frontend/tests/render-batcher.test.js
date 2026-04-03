import test from "node:test";
import assert from "node:assert/strict";

import { createRenderBatcher } from "../static/js/utils/render-batcher.js";

test("render batcher coalesces repeated schedule calls until the queued job runs", async () => {
  const calls = [];
  const queued = [];
  const batcher = createRenderBatcher((callback) => {
    queued.push(callback);
    return queued.length;
  });

  batcher.schedule("sidebar", () => {
    calls.push("first");
  });
  batcher.schedule("sidebar", () => {
    calls.push("second");
  });
  batcher.schedule("rail", () => {
    calls.push("rail");
  });

  assert.equal(queued.length, 2);

  queued.shift()();
  queued.shift()();

  assert.deepEqual(calls, ["second", "rail"]);
});

test("render batcher allows the same key to be scheduled again after execution", () => {
  const calls = [];
  const queued = [];
  const batcher = createRenderBatcher((callback) => {
    queued.push(callback);
    return queued.length;
  });

  batcher.schedule("sidebar", () => {
    calls.push("first");
  });
  queued.shift()();
  batcher.schedule("sidebar", () => {
    calls.push("second");
  });
  queued.shift()();

  assert.deepEqual(calls, ["first", "second"]);
});
