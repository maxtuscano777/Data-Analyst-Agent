"""Shared in-memory session store.

Imported by both main.py (upload endpoint writes) and sockets.py (WebSocket reads).
Keeping the store in a neutral module avoids circular imports.

Session dict shape (set at upload time, updated by WebSocket handler):
{
    "session_id":     str,           # UUID4
    "upload_paths":   list[str],     # absolute paths to session-scoped raw files
    "user_query":     str,
    "domain_context": str | None,
    "llm_model":      str,
    "data_profile":   dict,          # from generate_multi_file_profile()
    "status":         str,           # "uploaded" | "running" | "hitl_paused" | "complete" | "error"
}
"""

from __future__ import annotations

from typing import Any

_store: dict[str, dict[str, Any]] = {}


def create(session_id: str, data: dict[str, Any]) -> None:
    _store[session_id] = data


def get(session_id: str) -> dict[str, Any] | None:
    return _store.get(session_id)


def update(session_id: str, updates: dict[str, Any]) -> None:
    if session_id in _store:
        _store[session_id].update(updates)


def delete(session_id: str) -> None:
    _store.pop(session_id, None)
