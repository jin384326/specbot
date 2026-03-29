from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(frozen=True)
class BoardPost:
    post_id: str
    title: str
    body: str
    release_data: str
    release: str
    workspace_state: dict[str, Any]
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "postId": self.post_id,
            "title": self.title,
            "body": self.body,
            "releaseData": self.release_data,
            "release": self.release,
            "workspaceState": self.workspace_state,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
        }


@dataclass(frozen=True)
class BoardLock:
    post_id: str
    editor_id: str
    editor_label: str
    acquired_at: str
    expires_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "postId": self.post_id,
            "editorId": self.editor_id,
            "editorLabel": self.editor_label,
            "acquiredAt": self.acquired_at,
            "expiresAt": self.expires_at,
        }
