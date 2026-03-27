from __future__ import annotations

from pathlib import Path

import pytest

from app.clause_browser.backend.board_repository import BoardLockManager, BoardPostRepository, LockConflictError


def test_board_repository_create_and_update(tmp_path: Path) -> None:
    repository = BoardPostRepository(tmp_path / "posts.json")

    created = repository.create_post(title="First post", body="hello", workspace_state={"activeSpecNo": "23501"})
    updated = repository.update_post(
        post_id=created.post_id,
        title="Updated post",
        body="updated body",
        workspace_state={"activeSpecNo": "29512"},
    )

    assert updated.title == "Updated post"
    assert updated.body == "updated body"
    assert updated.workspace_state["activeSpecNo"] == "29512"
    assert repository.get_post(created.post_id).title == "Updated post"


def test_board_lock_conflict_blocks_second_editor(tmp_path: Path) -> None:
    locks = BoardLockManager(ttl_seconds=120)
    first = locks.acquire(post_id="post-1", editor_id="editor-a", editor_label="Alice")

    with pytest.raises(LockConflictError) as exc_info:
        locks.acquire(post_id="post-1", editor_id="editor-b", editor_label="Bob")

    assert first.editor_label == "Alice"
    assert exc_info.value.lock.editor_label == "Alice"
