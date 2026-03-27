from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.clause_browser.backend.board_repository import BoardLockManager, BoardPostRepository, LockConflictError


class BoardLockPayload(BaseModel):
    editorId: str = Field(min_length=1, max_length=120)
    editorLabel: str = Field(default="Anonymous", min_length=1, max_length=120)


class BoardCreatePayload(BoardLockPayload):
    title: str = Field(default="새 게시글", min_length=1, max_length=200)


class BoardUpdatePayload(BoardLockPayload):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(default="", max_length=20000)
    workspaceState: dict[str, Any] = Field(default_factory=dict)


def create_board_router(*, repository: BoardPostRepository, locks: BoardLockManager) -> APIRouter:
    router = APIRouter(prefix="/api/clause-browser/board", tags=["clause-board"])

    @router.get("/posts")
    def list_posts(query: str = "") -> dict[str, Any]:
        items = []
        for post in repository.list_posts(query=query):
            lock = locks.get_lock(post.post_id)
            items.append(
                {
                    **post.to_dict(),
                    "lock": lock.to_dict() if lock else None,
                }
            )
        return {"success": True, "data": {"items": items}}

    @router.post("/posts")
    def create_post(payload: BoardCreatePayload) -> dict[str, Any]:
        post = repository.create_post(title=payload.title, workspace_state={})
        lock = locks.acquire(post_id=post.post_id, editor_id=payload.editorId, editor_label=payload.editorLabel)
        return {"success": True, "data": {**post.to_dict(), "lock": lock.to_dict()}}

    @router.get("/posts/{post_id}")
    def get_post(post_id: str) -> dict[str, Any]:
        try:
            post = repository.get_post(post_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        lock = locks.get_lock(post_id)
        return {"success": True, "data": {**post.to_dict(), "lock": lock.to_dict() if lock else None}}

    @router.post("/posts/{post_id}/lock/acquire")
    def acquire_lock(post_id: str, payload: BoardLockPayload) -> dict[str, Any]:
        try:
            repository.get_post(post_id)
            lock = locks.acquire(post_id=post_id, editor_id=payload.editorId, editor_label=payload.editorLabel)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except LockConflictError as exc:
            raise HTTPException(status_code=409, detail={"message": str(exc), "lock": exc.lock.to_dict()}) from exc
        return {"success": True, "data": lock.to_dict()}

    @router.post("/posts/{post_id}/lock/heartbeat")
    def heartbeat_lock(post_id: str, payload: BoardLockPayload) -> dict[str, Any]:
        try:
            lock = locks.refresh(post_id=post_id, editor_id=payload.editorId, editor_label=payload.editorLabel)
        except LockConflictError as exc:
            raise HTTPException(status_code=409, detail={"message": str(exc), "lock": exc.lock.to_dict()}) from exc
        return {"success": True, "data": lock.to_dict()}

    @router.post("/posts/{post_id}/lock/release")
    def release_lock(post_id: str, payload: BoardLockPayload) -> dict[str, Any]:
        locks.release(post_id=post_id, editor_id=payload.editorId)
        return {"success": True, "data": {"released": True}}

    @router.put("/posts/{post_id}")
    def update_post(post_id: str, payload: BoardUpdatePayload) -> dict[str, Any]:
        current_lock = locks.get_lock(post_id)
        if current_lock and current_lock.editor_id != payload.editorId:
            raise HTTPException(
                status_code=409,
                detail={"message": f"Post is already being edited by {current_lock.editor_label}.", "lock": current_lock.to_dict()},
            )
        try:
            lock = locks.refresh(post_id=post_id, editor_id=payload.editorId, editor_label=payload.editorLabel)
            post = repository.update_post(
                post_id=post_id,
                title=payload.title,
                body=payload.body,
                workspace_state=payload.workspaceState,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except LockConflictError as exc:
            raise HTTPException(status_code=409, detail={"message": str(exc), "lock": exc.lock.to_dict()}) from exc
        return {"success": True, "data": {**post.to_dict(), "lock": lock.to_dict()}}

    return router
