import test from "node:test";
import assert from "node:assert/strict";

import {
  buildDeleteModalCopy,
  normalizeAdminDeletePassword,
} from "../static/js/features/board-delete-auth.js";

test("buildDeleteModalCopy returns post-specific copy", () => {
  assert.deepEqual(buildDeleteModalCopy({ kind: "post", title: "Post A" }), {
    eyebrow: "Delete Post",
    heading: "게시글을 삭제할까요?",
    body: "\"Post A\" 게시글을 정말 삭제할까요?",
  });
});

test("buildDeleteModalCopy returns board-specific copy", () => {
  assert.deepEqual(buildDeleteModalCopy({ kind: "board", title: "Board A" }), {
    eyebrow: "Delete Board",
    heading: "게시판을 삭제할까요?",
    body: "\"Board A\" 게시판을 정말 삭제할까요?",
  });
});

test("normalizeAdminDeletePassword trims and rejects empty values", () => {
  assert.equal(normalizeAdminDeletePassword("  secret  "), "secret");
  assert.throws(() => normalizeAdminDeletePassword("   "), /관리자 비밀번호를 입력하세요/);
});
