from __future__ import annotations

import json
import threading
import uuid
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.clause_browser.backend.board_domain import BoardLock, BoardPost, utc_now_iso


class BoardPostRepository:
    def __init__(self, storage_path: Path) -> None:
        self._storage_path = storage_path
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def list_posts(self, query: str = "") -> list[BoardPost]:
        posts = self._load_posts()
        normalized = query.strip().lower()
        if normalized:
            posts = [
                post
                for post in posts
                if normalized in post.title.lower() or normalized in post.body.lower()
            ]
        return sorted(posts, key=lambda item: (item.updated_at, item.created_at, item.post_id), reverse=True)

    def get_post(self, post_id: str) -> BoardPost:
        for post in self._load_posts():
            if post.post_id == post_id:
                return post
        raise KeyError(f"Unknown post: {post_id}")

    def create_post(self, *, title: str, body: str = "", workspace_state: dict[str, Any] | None = None) -> BoardPost:
        with self._lock:
            posts = self._load_posts_unlocked()
            now = utc_now_iso()
            post = BoardPost(
                post_id=uuid.uuid4().hex[:12],
                title=title.strip() or "Untitled post",
                body=body.strip(),
                workspace_state=dict(workspace_state or {}),
                created_at=now,
                updated_at=now,
            )
            posts.append(post)
            self._save_posts_unlocked(posts)
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
            posts = self._load_posts_unlocked()
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
            self._save_posts_unlocked(updated)
            return target

    def delete_post(self, post_id: str) -> None:
        with self._lock:
            posts = self._load_posts_unlocked()
            remaining = [post for post in posts if post.post_id != post_id]
            if len(remaining) == len(posts):
                raise KeyError(f"Unknown post: {post_id}")
            self._save_posts_unlocked(remaining)

    def _load_posts(self) -> list[BoardPost]:
        with self._lock:
            return self._load_posts_unlocked()

    def _load_posts_unlocked(self) -> list[BoardPost]:
        if not self._storage_path.exists():
            return []
        payload = json.loads(self._storage_path.read_text(encoding="utf-8"))
        return [
            BoardPost(
                post_id=str(item.get("postId") or ""),
                title=str(item.get("title") or ""),
                body=str(item.get("body") or ""),
                workspace_state=dict(item.get("workspaceState") or {}),
                created_at=str(item.get("createdAt") or ""),
                updated_at=str(item.get("updatedAt") or ""),
            )
            for item in payload.get("posts", [])
            if str(item.get("postId") or "").strip()
        ]

    def _save_posts_unlocked(self, posts: list[BoardPost]) -> None:
        payload = {"posts": [post.to_dict() for post in posts]}
        self._storage_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


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
