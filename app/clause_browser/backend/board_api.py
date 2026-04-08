from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.clause_browser.backend.board_repository import BoardDeletionError, BoardLockManager, BoardPostRepository, LockConflictError


class BoardLockPayload(BaseModel):
    editorId: str = Field(min_length=1, max_length=120)
    editorLabel: str = Field(default="Anonymous", min_length=1, max_length=120)


class BoardAdminDeletePayload(BaseModel):
    adminPassword: str = Field(min_length=1, max_length=200)


class BoardDeletePayload(BoardLockPayload):
    adminPassword: str = Field(min_length=1, max_length=200)


class BoardCreatePayload(BoardLockPayload):
    boardId: str = Field(default="default", min_length=1, max_length=120)
    title: str = Field(default="새 게시글", min_length=1, max_length=200)
    body: str = Field(default="", max_length=20000)
    releaseData: str = Field(min_length=1, max_length=32)
    release: str = Field(min_length=1, max_length=32)
    workspaceState: dict[str, Any] = Field(default_factory=dict)


class BoardUpdatePayload(BoardLockPayload):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(default="", max_length=20000)
    workspaceState: dict[str, Any] = Field(default_factory=dict)


class BoardListCreatePayload(BaseModel):
    name: str = Field(min_length=1, max_length=120)


def create_board_router(*, repository: BoardPostRepository, locks: BoardLockManager) -> APIRouter:
    router = APIRouter(prefix="/api/clause-browser/board", tags=["clause-board"])

    def require_admin_password(admin_password: str) -> None:
        configured_password = str(os.environ.get("CLAUSE_BROWSER_ADMIN_PASSWORD") or "").strip()
        if not configured_password:
            raise HTTPException(status_code=503, detail={"message": "관리자 삭제 비밀번호가 설정되지 않았습니다."})
        if str(admin_password or "") != configured_password:
            raise HTTPException(status_code=403, detail={"message": "관리자 비밀번호가 올바르지 않습니다."})

    @router.get("/posts")
    def list_posts(query: str = "", boardId: str = "") -> dict[str, Any]:
        items = []
        for post in repository.list_posts(query=query, board_id=boardId):
            lock = locks.get_lock(post.post_id)
            items.append(
                {
                    **post.to_dict(),
                    "lock": lock.to_dict() if lock else None,
                }
            )
        return {"success": True, "data": {"items": items}}

    @router.get("/boards")
    def list_boards() -> dict[str, Any]:
        return {"success": True, "data": {"items": [board.to_dict() for board in repository.list_boards()]}}

    @router.post("/boards")
    def create_board(payload: BoardListCreatePayload) -> dict[str, Any]:
        board = repository.create_board(name=payload.name)
        return {"success": True, "data": board.to_dict()}

    @router.post("/boards/{board_id}/delete")
    def delete_board(board_id: str, payload: BoardAdminDeletePayload) -> dict[str, Any]:
        require_admin_password(payload.adminPassword)
        try:
            repository.delete_board(board_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except BoardDeletionError as exc:
            raise HTTPException(status_code=409, detail={"message": str(exc)}) from exc
        return {"success": True, "data": {"deleted": True, "boardId": board_id}}

    @router.post("/posts")
    def create_post(payload: BoardCreatePayload) -> dict[str, Any]:
        post = repository.create_post(
            board_id=payload.boardId,
            title=payload.title,
            body=payload.body,
            release_data=payload.releaseData,
            release=payload.release,
            workspace_state=payload.workspaceState,
        )
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
            post = repository.update_post(
                post_id=post_id,
                title=payload.title,
                body=payload.body,
                workspace_state=payload.workspaceState,
            )
            lock = (
                locks.refresh(post_id=post_id, editor_id=payload.editorId, editor_label=payload.editorLabel)
                if current_lock and current_lock.editor_id == payload.editorId
                else None
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except LockConflictError as exc:
            raise HTTPException(status_code=409, detail={"message": str(exc), "lock": exc.lock.to_dict()}) from exc
        return {"success": True, "data": {**post.to_dict(), "lock": lock.to_dict() if lock else None}}

    @router.post("/posts/{post_id}/delete")
    def delete_post(post_id: str, payload: BoardDeletePayload) -> dict[str, Any]:
        require_admin_password(payload.adminPassword)
        current_lock = locks.get_lock(post_id)
        if current_lock:
            raise HTTPException(
                status_code=409,
                detail={"message": f"Post is already being edited by {current_lock.editor_label}.", "lock": current_lock.to_dict()},
            )
        try:
            repository.delete_post(post_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        locks.clear(post_id=post_id)
        return {"success": True, "data": {"deleted": True, "postId": post_id}}

    return router
