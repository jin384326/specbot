export function buildDeleteModalCopy(target = {}) {
  const title = String(target?.title || "").trim() || "이 항목";
  if (target?.kind === "board") {
    return {
      eyebrow: "Delete Board",
      heading: "게시판을 삭제할까요?",
      body: `"${title}" 게시판을 정말 삭제할까요?`,
    };
  }
  return {
    eyebrow: "Delete Post",
    heading: "게시글을 삭제할까요?",
    body: `"${title}" 게시글을 정말 삭제할까요?`,
  };
}

export function normalizeAdminDeletePassword(value) {
  const password = String(value || "").trim();
  if (!password) {
    throw new Error("관리자 비밀번호를 입력하세요.");
  }
  return password;
}
