"""Async SQLite persistence layer for ADAW session history.

All public functions are async and safe to call from FastAPI route handlers
and the WebSocket handler. The DB file is created automatically on first call
to init_db().
"""

from __future__ import annotations

import json
from pathlib import Path

import aiosqlite

_DB_PATH = Path(__file__).parent.parent / "adaw.db"


# ── Schema init ────────────────────────────────────────────────────────────────

async def init_db() -> None:
    """Create tables if they don't exist. Called once at FastAPI startup."""
    async with aiosqlite.connect(_DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id           TEXT PRIMARY KEY,
                user_query           TEXT NOT NULL,
                domain_context       TEXT,
                llm_model            TEXT,
                file_names           TEXT,
                status               TEXT DEFAULT 'uploaded',
                created_at           TEXT DEFAULT (datetime('now')),
                final_chart_paths    TEXT,
                executive_summary_md TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS session_logs (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL REFERENCES sessions(session_id),
                node       TEXT,
                content    TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS session_nodes (
                session_id TEXT NOT NULL REFERENCES sessions(session_id),
                node_name  TEXT NOT NULL,
                status     TEXT DEFAULT 'pending',
                summary    TEXT,
                PRIMARY KEY (session_id, node_name)
            )
        """)
        await db.commit()


# ── Write operations ───────────────────────────────────────────────────────────

async def create_session(
    session_id: str,
    user_query: str,
    domain_context: str | None,
    llm_model: str,
    file_names: list[str],
) -> None:
    """Insert a new session row at upload time. Uses INSERT OR IGNORE so a
    duplicate call (e.g., on retry) is a no-op."""
    async with aiosqlite.connect(_DB_PATH) as db:
        await db.execute(
            """INSERT OR IGNORE INTO sessions
               (session_id, user_query, domain_context, llm_model, file_names)
               VALUES (?, ?, ?, ?, ?)""",
            (session_id, user_query, domain_context, llm_model, json.dumps(file_names)),
        )
        await db.commit()


async def update_session(session_id: str, **kwargs) -> None:
    """Update arbitrary columns on a session row. Keyword args map to column names."""
    if not kwargs:
        return
    cols = ", ".join(f"{k} = ?" for k in kwargs)
    vals = list(kwargs.values()) + [session_id]
    async with aiosqlite.connect(_DB_PATH) as db:
        await db.execute(f"UPDATE sessions SET {cols} WHERE session_id = ?", vals)
        await db.commit()


async def save_logs(session_id: str, logs: list[dict]) -> None:
    """Batch-insert WebSocket log messages. Each dict must have 'node' and 'content'."""
    if not logs:
        return
    rows = [(session_id, entry["node"], entry["content"]) for entry in logs]
    async with aiosqlite.connect(_DB_PATH) as db:
        await db.executemany(
            "INSERT INTO session_logs (session_id, node, content) VALUES (?, ?, ?)",
            rows,
        )
        await db.commit()


async def save_nodes(session_id: str, nodes: list[dict]) -> None:
    """Upsert node completion records. Each dict must have 'node_name', 'status',
    and optionally 'summary' (a JSON-serialised dict)."""
    if not nodes:
        return
    rows = [
        (session_id, n["node_name"], n["status"], n.get("summary"))
        for n in nodes
    ]
    async with aiosqlite.connect(_DB_PATH) as db:
        await db.executemany(
            """INSERT OR REPLACE INTO session_nodes
               (session_id, node_name, status, summary) VALUES (?, ?, ?, ?)""",
            rows,
        )
        await db.commit()


# ── Read operations ────────────────────────────────────────────────────────────

async def list_sessions() -> list[dict]:
    """Return all session rows ordered newest-first, without logs or nodes."""
    async with aiosqlite.connect(_DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM sessions ORDER BY created_at DESC"
        ) as cursor:
            rows = await cursor.fetchall()

    result = []
    for row in rows:
        s = dict(row)
        if s.get("file_names"):
            s["file_names"] = json.loads(s["file_names"])
        if s.get("final_chart_paths"):
            s["final_chart_paths"] = json.loads(s["final_chart_paths"])
        result.append(s)
    return result


async def get_session(session_id: str) -> dict | None:
    """Return a single session with its full logs and node records, or None."""
    async with aiosqlite.connect(_DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        async with db.execute(
            "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
        ) as cursor:
            row = await cursor.fetchone()
        if not row:
            return None
        session = dict(row)

        async with db.execute(
            "SELECT node, content FROM session_logs WHERE session_id = ? ORDER BY id",
            (session_id,),
        ) as cursor:
            logs = [dict(r) for r in await cursor.fetchall()]

        async with db.execute(
            "SELECT node_name, status, summary FROM session_nodes WHERE session_id = ?",
            (session_id,),
        ) as cursor:
            nodes = [dict(r) for r in await cursor.fetchall()]

    if session.get("file_names"):
        session["file_names"] = json.loads(session["file_names"])
    if session.get("final_chart_paths"):
        session["final_chart_paths"] = json.loads(session["final_chart_paths"])
    for node in nodes:
        if node.get("summary"):
            node["summary"] = json.loads(node["summary"])

    session["logs"] = logs
    session["nodes"] = nodes
    return session
