"""WebSocket handlers for ADAW.

Two channels:
  /ws/logs   — streams raw agent execution logs to the React terminal UI
  /ws/hitl   — manages the Human-in-the-Loop pause/approval cycle
"""

import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()


@router.websocket("/ws/logs")
async def ws_agent_logs(websocket: WebSocket):
    """Stream agent execution logs to the frontend Live Terminal component."""
    await websocket.accept()
    try:
        # TODO Phase 3: subscribe to log event queue produced by LangGraph runner
        await websocket.send_json({"type": "info", "message": "Log stream connected."})
        while True:
            # Keep connection alive; actual log events pushed from agent runner
            data = await websocket.receive_text()
            # Echo back for now (placeholder)
            await websocket.send_json({"type": "echo", "message": data})
    except WebSocketDisconnect:
        pass


@router.websocket("/ws/hitl")
async def ws_hitl(websocket: WebSocket):
    """Human-in-the-Loop pause/approval channel.

    Lifecycle:
      1. Server sends {"type": "hitl_pause", "charts": [...base64 images...]}
      2. Client sends {"action": "approve"} or {"action": "revise", "feedback": "..."}
      3. Server resumes or re-invokes LangGraph accordingly.
    """
    await websocket.accept()
    try:
        # TODO Phase 3: wire to LangGraph MemorySaver checkpoint and interrupt handler
        await websocket.send_json({"type": "info", "message": "HITL channel connected."})
        while True:
            raw = await websocket.receive_text()
            payload = json.loads(raw)
            action = payload.get("action")
            if action == "approve":
                await websocket.send_json({"type": "status", "message": "Approved. Resuming graph."})
            elif action == "revise":
                feedback = payload.get("feedback", "")
                await websocket.send_json({"type": "status", "message": f"Revision requested: {feedback}"})
            else:
                await websocket.send_json({"type": "error", "message": f"Unknown action: {action}"})
    except WebSocketDisconnect:
        pass
