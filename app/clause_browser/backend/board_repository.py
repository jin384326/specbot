from __future__ import annotations

import json
import threading
import uuid
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.clause_browser.backend.board_domain import Board, BoardLock, BoardPost, utc_now_iso

DEFAULT_BOARD_ID = "default"
DEFAULT_BOARD_NAME = "기본 게시판"


class BoardPostRepository:
    def __init__(self, storage_path: Path) -> None:
        self._storage_path = storage_path
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def list_boards(self) -> list[Board]:
        boards, _posts = self._load_state()
        return boards

    def create_board(self, *, name: str) -> Board:
        normalized_name = name.strip() or "새 게시판"
        with self._lock:
            boards, posts = self._load_state_unlocked()
            now = utc_now_iso()
            board = Board(
                board_id=uuid.uuid4().hex[:12],
                name=normalized_name,
                created_at=now,
                updated_at=now,
            )
            self._save_state_unlocked([*boards, board], posts)
            return board

    def delete_board(self, board_id: str) -> None:
        normalized_board_id = board_id.strip()
        if not normalized_board_id:
            raise KeyError("Unknown board: ")
        if normalized_board_id == DEFAULT_BOARD_ID:
            raise BoardDeletionError("기본 게시판은 삭제할 수 없습니다.")
        with self._lock:
            boards, posts = self._load_state_unlocked()
            if any(post.board_id == normalized_board_id for post in posts):
                raise BoardDeletionError("게시글이 남아 있는 게시판은 삭제할 수 없습니다.")
            remaining = [board for board in boards if board.board_id != normalized_board_id]
            if len(remaining) == len(boards):
                raise KeyError(f"Unknown board: {normalized_board_id}")
            self._save_state_unlocked(remaining, posts)

    def list_posts(self, query: str = "", board_id: str = "") -> list[BoardPost]:
        _boards, posts = self._load_state()
        normalized = query.strip().lower()
        normalized_board_id = board_id.strip()
        if normalized_board_id:
            posts = [post for post in posts if post.board_id == normalized_board_id]
        if normalized:
            posts = [
                post
                for post in posts
                if normalized in post.title.lower() or normalized in post.body.lower()
            ]
        return sorted(posts, key=lambda item: (item.created_at, item.post_id), reverse=True)

    def get_post(self, post_id: str) -> BoardPost:
        _boards, posts = self._load_state()
        for post in posts:
            if post.post_id == post_id:
                return post
        raise KeyError(f"Unknown post: {post_id}")

    def create_post(
        self,
        *,
        board_id: str = DEFAULT_BOARD_ID,
        title: str,
        body: str = "",
        release_data: str,
        release: str,
        workspace_state: dict[str, Any] | None = None,
    ) -> BoardPost:
        with self._lock:
            boards, posts = self._load_state_unlocked()
            normalized_board_id = board_id.strip() or DEFAULT_BOARD_ID
            if not any(board.board_id == normalized_board_id for board in boards):
                raise KeyError(f"Unknown board: {normalized_board_id}")
            now = utc_now_iso()
            post = BoardPost(
                post_id=uuid.uuid4().hex[:12],
                board_id=normalized_board_id,
                title=title.strip() or "Untitled post",
                body=body.strip(),
                release_data=release_data.strip(),
                release=release.strip(),
                workspace_state=dict(workspace_state or {}),
                created_at=now,
                updated_at=now,
            )
            posts.append(post)
            self._save_state_unlocked(boards, posts)
            return post

    def update_post(
        self,
        *,
        post_id: str,
        title: str,
        body: str,
        workspace_state: dict[str, Any],
    ) -> BoardPost:
        with self._lock:
            boards, posts = self._load_state_unlocked()
            updated: list[BoardPost] = []
            target: BoardPost | None = None
            for post in posts:
                if post.post_id != post_id:
                    updated.append(post)
                    continue
                target = replace(
                    post,
                    title=title.strip() or post.title,
                    body=body.strip(),
                    workspace_state=dict(workspace_state or {}),
                    updated_at=utc_now_iso(),
                )
                updated.append(target)
            if target is None:
                raise KeyError(f"Unknown post: {post_id}")
            self._save_state_unlocked(boards, updated)
            return target

    def delete_post(self, post_id: str) -> None:
        with self._lock:
            boards, posts = self._load_state_unlocked()
            remaining = [post for post in posts if post.post_id != post_id]
            if len(remaining) == len(posts):
                raise KeyError(f"Unknown post: {post_id}")
            self._save_state_unlocked(boards, remaining)

    def _load_state(self) -> tuple[list[Board], list[BoardPost]]:
        with self._lock:
            return self._load_state_unlocked()

    def _load_state_unlocked(self) -> tuple[list[Board], list[BoardPost]]:
        if not self._storage_path.exists():
            return self._default_boards(), []
        payload = json.loads(self._storage_path.read_text(encoding="utf-8"))
        boards = [
            Board(
                board_id=str(item.get("boardId") or ""),
                name=str(item.get("name") or ""),
                created_at=str(item.get("createdAt") or ""),
                updated_at=str(item.get("updatedAt") or ""),
            )
            for item in payload.get("boards", [])
            if str(item.get("boardId") or "").strip()
        ]
        if not boards:
            boards = self._default_boards()
        elif not any(board.board_id == DEFAULT_BOARD_ID for board in boards):
            boards = [*self._default_boards(), *boards]
        posts = [
            BoardPost(
                post_id=str(item.get("postId") or ""),
                board_id=str(item.get("boardId") or DEFAULT_BOARD_ID),
                title=str(item.get("title") or ""),
                body=str(item.get("body") or ""),
                release_data=str(item.get("releaseData") or ""),
                release=str(item.get("release") or ""),
                workspace_state=dict(item.get("workspaceState") or {}),
                created_at=str(item.get("createdAt") or ""),
                updated_at=str(item.get("updatedAt") or ""),
            )
            for item in payload.get("posts", [])
            if str(item.get("postId") or "").strip()
        ]
        return boards, posts

    def _save_state_unlocked(self, boards: list[Board], posts: list[BoardPost]) -> None:
        payload = {
            "boards": [board.to_dict() for board in boards],
            "posts": [post.to_dict() for post in posts],
        }
        self._storage_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _default_boards(self) -> list[Board]:
        now = utc_now_iso()
        return [
            Board(
                board_id=DEFAULT_BOARD_ID,
                name=DEFAULT_BOARD_NAME,
                created_at=now,
                updated_at=now,
            )
        ]


class BoardLockManager:
    def __init__(self, *, ttl_seconds: int = 120) -> None:
        self._ttl_seconds = ttl_seconds
        self._lock = threading.Lock()
        self._locks: dict[str, BoardLock] = {}

    def get_lock(self, post_id: str) -> BoardLock | None:
        with self._lock:
            self._purge_expired_unlocked()
            return self._locks.get(post_id)

    def acquire(self, *, post_id: str, editor_id: str, editor_label: str) -> BoardLock:
        with self._lock:
            self._purge_expired_unlocked()
            existing = self._locks.get(post_id)
            if existing and existing.editor_id != editor_id:
                raise LockConflictError(existing)
            lock = self._build_lock(post_id=post_id, editor_id=editor_id, editor_label=editor_label)
            self._locks[post_id] = lock
            return lock

    def refresh(self, *, post_id: str, editor_id: str, editor_label: str) -> BoardLock:
        with self._lock:
            self._purge_expired_unlocked()
            existing = self._locks.get(post_id)
            if existing and existing.editor_id != editor_id:
                raise LockConflictError(existing)
            lock = self._build_lock(post_id=post_id, editor_id=editor_id, editor_label=editor_label)
            self._locks[post_id] = lock
            return lock

    def release(self, *, post_id: str, editor_id: str) -> None:
        with self._lock:
            existing = self._locks.get(post_id)
            if existing and existing.editor_id == editor_id:
                self._locks.pop(post_id, None)

    def clear(self, *, post_id: str) -> None:
        with self._lock:
            self._locks.pop(post_id, None)

    def _build_lock(self, *, post_id: str, editor_id: str, editor_label: str) -> BoardLock:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        expires_at = now + timedelta(seconds=self._ttl_seconds)
        return BoardLock(
            post_id=post_id,
            editor_id=editor_id,
            editor_label=editor_label.strip() or editor_id,
            acquired_at=now.isoformat(),
            expires_at=expires_at.isoformat(),
        )

    def _purge_expired_unlocked(self) -> None:
        now = datetime.now(timezone.utc)
        expired = [
            post_id
            for post_id, lock in self._locks.items()
            if datetime.fromisoformat(lock.expires_at) <= now
        ]
        for post_id in expired:
            self._locks.pop(post_id, None)


class LockConflictError(RuntimeError):
    def __init__(self, lock: BoardLock) -> None:
        super().__init__(f"Post is already being edited by {lock.editor_label}.")
        self.lock = lock


class BoardDeletionError(RuntimeError):
    pass
