from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.api import sessions as session_store
from backend.api.data_profiler import generate_multi_file_profile
from backend.api.sockets import router as ws_router

app = FastAPI(
    title="ADAW — Autonomous B2B Data Analyst Workspace",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# WebSocket routes (/ws/pipeline/{session_id})
app.include_router(ws_router)

# ── Directory constants ────────────────────────────────────────────────────────
_BACKEND_DIR   = Path(__file__).parent.parent
_RAW_UPLOADS_DIR = _BACKEND_DIR / "uploads" / "raw"
_CHARTS_DIR    = _BACKEND_DIR / "charts"


# ── REST Endpoints ─────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/upload")
async def upload_files(
    files: list[UploadFile] = File(...),
    user_query: str = Form(...),
    domain_context: Optional[str] = Form(None),
    llm_model: str = Form("gemini-2.5-flash"),
):
    """Accept one or more CSV/Excel files and the user's business goal.

    Saves each file to a session-scoped subdirectory under uploads/raw/,
    profiles the data (no LLM), stores the session in memory, and returns
    the session_id + data profile so the client can open the WebSocket.
    """
    session_id = str(uuid.uuid4())
    session_dir = _RAW_UPLOADS_DIR / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    upload_paths: list[str] = []
    for upload in files:
        dest = session_dir / upload.filename
        with dest.open("wb") as f:
            shutil.copyfileobj(upload.file, f)
        upload_paths.append(str(dest))

    # Profile all uploaded files (pure pandas — no LLM)
    data_profile = generate_multi_file_profile(upload_paths)

    session_store.create(session_id, {
        "session_id":     session_id,
        "upload_paths":   upload_paths,
        "user_query":     user_query,
        "domain_context": domain_context,
        "llm_model":      llm_model,
        "data_profile":   data_profile,
        "status":         "uploaded",
    })

    return {
        "session_id":   session_id,
        "file_names":   [Path(p).name for p in upload_paths],
        "data_profile": data_profile,
    }


@app.get("/session/{session_id}")
async def get_session(session_id: str):
    """Return the current status and metadata of a session."""
    session = session_store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "session_id":  session["session_id"],
        "status":      session["status"],
        "file_names":  [Path(p).name for p in session["upload_paths"]],
        "user_query":  session["user_query"],
    }


# ── Static file mounts ────────────────────────────────────────────────────────
# Charts must be mounted BEFORE the React catch-all so /charts/* is handled first.
_CHARTS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/charts", StaticFiles(directory=str(_CHARTS_DIR)), name="charts")

# Serve compiled React build in production (copied to backend/static by Dockerfile)
_static_dir = _BACKEND_DIR / "static"
if _static_dir.exists() and any(_static_dir.iterdir()):
    app.mount("/", StaticFiles(directory=str(_static_dir), html=True), name="static")
