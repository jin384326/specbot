from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.routing import APIRoute

from app.clause_browser.backend.board_api import BoardCreatePayload, create_board_router
from app.clause_browser.backend.board_repository import BoardDeletionError, BoardLockManager, BoardPostRepository, LockConflictError


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
            boardId="default",
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


def test_board_repository_lists_posts_by_created_at_descending(tmp_path: Path) -> None:
    repository = BoardPostRepository(tmp_path / "posts.json")
    first = repository.create_post(
        title="First post",
        board_id="default",
        release_data="2025-12",
        release="Rel-18",
    )
    second = repository.create_post(
        title="Second post",
        board_id="default",
        release_data="2025-12",
        release="Rel-18",
    )

    updated_first = repository.update_post(
        post_id=first.post_id,
        title="First post updated",
        body="edited",
        workspace_state={},
    )

    listed = repository.list_posts(board_id="default")

    assert [item.post_id for item in listed] == [second.post_id, updated_first.post_id]


def test_board_repository_creates_and_lists_boards(tmp_path: Path) -> None:
    repository = BoardPostRepository(tmp_path / "posts.json")

    created = repository.create_board(name="QA Board")
    boards = repository.list_boards()

    assert boards[0].board_id == "default"
    assert [item.board_id for item in boards] == ["default", created.board_id]
    assert boards[1].name == "QA Board"


def test_board_router_lists_boards_and_filters_posts_by_board(tmp_path: Path) -> None:
    repository = BoardPostRepository(tmp_path / "posts.json")
    locks = BoardLockManager(ttl_seconds=120)
    router = create_board_router(repository=repository, locks=locks)

    custom_board = repository.create_board(name="Custom")
    default_post = repository.create_post(
        title="Default post",
        board_id="default",
        release_data="2025-12",
        release="Rel-18",
    )
    custom_post = repository.create_post(
        title="Custom post",
        board_id=custom_board.board_id,
        release_data="2025-12",
        release="Rel-18",
    )

    list_boards_endpoint = next(
        route.endpoint
        for route in router.routes
        if isinstance(route, APIRoute) and route.path == "/api/clause-browser/board/boards" and "GET" in route.methods
    )
    list_posts_endpoint = next(
        route.endpoint
        for route in router.routes
        if isinstance(route, APIRoute) and route.path == "/api/clause-browser/board/posts" and "GET" in route.methods
    )

    boards_response = list_boards_endpoint()
    posts_response = list_posts_endpoint(query="", boardId=custom_board.board_id)

    assert [item["boardId"] for item in boards_response["data"]["items"]] == ["default", custom_board.board_id]
    assert [item["postId"] for item in posts_response["data"]["items"]] == [custom_post.post_id]
    assert default_post.post_id not in [item["postId"] for item in posts_response["data"]["items"]]


def test_board_repository_deletes_empty_board(tmp_path: Path) -> None:
    repository = BoardPostRepository(tmp_path / "posts.json")
    created = repository.create_board(name="To Delete")

    repository.delete_board(created.board_id)

    assert [item.board_id for item in repository.list_boards()] == ["default"]


def test_board_repository_rejects_deleting_non_empty_board(tmp_path: Path) -> None:
    repository = BoardPostRepository(tmp_path / "posts.json")
    created = repository.create_board(name="Busy Board")
    repository.create_post(
        title="Existing post",
        board_id=created.board_id,
        release_data="2025-12",
        release="Rel-18",
    )

    with pytest.raises(BoardDeletionError):
        repository.delete_board(created.board_id)


def test_board_router_rejects_deleting_non_empty_board(tmp_path: Path) -> None:
    repository = BoardPostRepository(tmp_path / "posts.json")
    locks = BoardLockManager(ttl_seconds=120)
    router = create_board_router(repository=repository, locks=locks)
    created = repository.create_board(name="Busy Board")
    repository.create_post(
        title="Existing post",
        board_id=created.board_id,
        release_data="2025-12",
        release="Rel-18",
    )
    delete_board_endpoint = next(
        route.endpoint
        for route in router.routes
        if isinstance(route, APIRoute) and route.path == "/api/clause-browser/board/boards/{board_id}/delete" and "POST" in route.methods
    )

    with pytest.raises(Exception) as exc_info:
        delete_board_endpoint(created.board_id)

    assert getattr(exc_info.value, "status_code", None) == 409
