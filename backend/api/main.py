from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from backend.api.sockets import router as ws_router

app = FastAPI(
    title="ADAW — Autonomous B2B Data Analyst Workspace",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# WebSocket routes
app.include_router(ws_router)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/upload")
async def upload_file():
    # TODO Phase 1: accept UploadFile, save to /uploads, log session to SQLite
    return {"message": "not implemented"}


# Serve compiled React build in production (copied to backend/static by Dockerfile)
_static_dir = Path(__file__).parent.parent / "static"
if _static_dir.exists() and any(_static_dir.iterdir()):
    app.mount("/", StaticFiles(directory=str(_static_dir), html=True), name="static")
