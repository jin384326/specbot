from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.routing import APIRoute

from app.clause_browser.backend.board_api import BoardCreatePayload, create_board_router
from app.clause_browser.backend.board_repository import BoardLockManager, BoardPostRepository, LockConflictError


def test_board_repository_create_and_update(tmp_path: Path) -> None:
    repository = BoardPostRepository(tmp_path / "posts.json")

    created = repository.create_post(
        title="First post",
        body="hello",
        release_data="2025-12",
        release="Rel-18",
        workspace_state={"activeSpecNo": "23501"},
    )
    updated = repository.update_post(
        post_id=created.post_id,
        title="Updated post",
        body="updated body",
        workspace_state={"activeSpecNo": "29512"},
    )

    assert updated.title == "Updated post"
    assert updated.body == "updated body"
    assert updated.release_data == "2025-12"
    assert updated.release == "Rel-18"
    assert updated.workspace_state["activeSpecNo"] == "29512"
    assert repository.get_post(created.post_id).title == "Updated post"


def test_board_repository_delete_removes_post(tmp_path: Path) -> None:
    repository = BoardPostRepository(tmp_path / "posts.json")
    created = repository.create_post(title="Delete me", release_data="2025-12", release="Rel-18")

    repository.delete_post(created.post_id)

    with pytest.raises(KeyError):
        repository.get_post(created.post_id)


def test_board_lock_conflict_blocks_second_editor(tmp_path: Path) -> None:
    locks = BoardLockManager(ttl_seconds=120)
    first = locks.acquire(post_id="post-1", editor_id="editor-a", editor_label="Alice")

    with pytest.raises(LockConflictError) as exc_info:
        locks.acquire(post_id="post-1", editor_id="editor-b", editor_label="Bob")

    assert first.editor_label == "Alice"
    assert exc_info.value.lock.editor_label == "Alice"


def test_board_lock_clear_releases_post_lock() -> None:
    locks = BoardLockManager(ttl_seconds=120)
    locks.acquire(post_id="post-1", editor_id="editor-a", editor_label="Alice")

    locks.clear(post_id="post-1")

    assert locks.get_lock("post-1") is None


def test_board_create_api_persists_workspace_state(tmp_path: Path) -> None:
    repository = BoardPostRepository(tmp_path / "posts.json")
    locks = BoardLockManager(ttl_seconds=120)
    router = create_board_router(repository=repository, locks=locks)
    endpoint = next(
        route.endpoint
        for route in router.routes
        if isinstance(route, APIRoute) and route.path == "/api/clause-browser/board/posts" and "POST" in route.methods
    )

    response = endpoint(
        BoardCreatePayload(
            editorId="editor-a",
            editorLabel="Alice",
            title="Draft",
            body="",
            releaseData="2025-12",
            release="Rel-18",
            workspaceState={"loadedRoots": [{"key": "23501:4"}], "activeSpecNo": "23501"},
        )
    )

    post_id = response["data"]["postId"]
    saved = repository.get_post(post_id)
    assert saved.release_data == "2025-12"
    assert saved.release == "Rel-18"
    assert saved.workspace_state["activeSpecNo"] == "23501"
    assert saved.workspace_state["loadedRoots"][0]["key"] == "23501:4"
