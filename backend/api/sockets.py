"""WebSocket handler for the ADAW pipeline.

Single channel per session: /ws/pipeline/{session_id}

Lifecycle:
  1. Client POSTs to /upload → receives session_id.
  2. Client opens ws://host/ws/pipeline/{session_id}.
  3. Server builds initial AgentState and calls graph.astream().
  4. Server emits events as each node completes:
       node_start  → signals node has begun (client shows spinner)
       log         → one entry per execution_log line (client appends to terminal)
       node_complete → compact summary of node output (client updates dashboard)
  5. graph.astream() exhausts when the graph hits interrupt_before=["executive_presenter"].
  6. Server emits hitl_pause with draft chart URLs and analysis insights.
  7. Client sends {"action": "approve"} or {"action": "revise", "feedback": "..."}.
  8. Server resumes graph via graph.update_state() + graph.astream(None, ...).
  9. Server emits pipeline_complete with final chart URLs and executive Markdown.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.api import sessions as session_store
from backend.agents.graph import graph
from backend.schemas.output_schemas import AnalysisResult, CleaningResult, PresentationResult

router = APIRouter()

_NODE_DISPLAY: dict[str, str] = {
    "chief_planner":       "Chief Planner",
    "data_engineer":       "Data Engineer",
    "statistical_analyst": "Statistical Analyst",
    "executive_presenter": "Executive Presenter",
}

# Root of the charts directory — used to build relative /charts/... URLs
_CHARTS_ROOT = Path(__file__).parent.parent / "charts"


# ── Helpers ────────────────────────────────────────────────────────────────────

def _serialize_result(result: Any) -> dict:
    """Convert a Pydantic result model to a JSON-safe summary dict.

    execution_log is excluded here — log entries are sent separately as
    individual "log" WebSocket messages so the frontend can render them
    incrementally without waiting for a large payload.
    """
    if isinstance(result, CleaningResult):
        return {
            "rows_before":      result.rows_before,
            "rows_after":       result.rows_after,
            "columns_dropped":  result.columns_dropped,
            "cleaned_csv_path": result.cleaned_csv_path,
        }
    if isinstance(result, AnalysisResult):
        return {
            "insights":          result.insights,
            "model_evaluations": [me.model_dump() for me in result.model_evaluations],
            "draft_chart_paths": result.draft_chart_paths,
        }
    if isinstance(result, PresentationResult):
        return {
            "final_chart_paths":    result.final_chart_paths,
            "executive_summary_md": result.executive_summary_md,
        }
    if hasattr(result, "model_dump"):
        return result.model_dump()
    return {}


def _chart_urls(chart_paths: list[str]) -> list[str]:
    """Convert absolute PNG paths to relative /charts/... HTTP URLs.

    The /charts static mount in main.py makes these paths directly fetchable
    by the browser without a separate API endpoint.
    """
    urls = []
    for p in chart_paths:
        try:
            rel = Path(p).relative_to(_CHARTS_ROOT)
            urls.append(f"/charts/{rel.as_posix()}")
        except ValueError:
            urls.append(p)  # fallback: send raw absolute path
    return urls


# ── WebSocket handler ──────────────────────────────────────────────────────────

@router.websocket("/ws/pipeline/{session_id}")
async def ws_pipeline(websocket: WebSocket, session_id: str):
    await websocket.accept()

    session = session_store.get(session_id)
    if not session:
        await websocket.send_json({"type": "error", "message": "Session not found."})
        await websocket.close()
        return

    config = {"configurable": {"thread_id": session_id}}

    initial_state = {
        "session_id":          session_id,
        "upload_paths":        session["upload_paths"],
        "user_query":          session["user_query"],
        "domain_context":      session["domain_context"],
        "data_profile":        session["data_profile"],
        "plan":                None,
        "llm_model":           session["llm_model"],
        "hitl_approved":       False,
        "hitl_feedback":       None,
        "messages":            [],
        "cleaning_result":     None,
        "analysis_result":     None,
        "presentation_result": None,
    }

    session_store.update(session_id, {"status": "running"})

    try:
        # ── Phase 1: chief_planner → data_engineer → statistical_analyst ──────
        current_node: str | None = None

        async for event in graph.astream(initial_state, config=config, stream_mode="updates"):
            for node_name, updates in event.items():
                if node_name.startswith("__"):  # skip LangGraph internal signals (__interrupt__, __end__, etc.)
                    continue

                # Emit node_start on first update from a new node
                if node_name != current_node:
                    current_node = node_name
                    await websocket.send_json({
                        "type":         "node_start",
                        "node":         node_name,
                        "display_name": _NODE_DISPLAY.get(node_name, node_name),
                    })

                # Burst-send execution_log entries as individual log messages
                for result_key in ("cleaning_result", "analysis_result", "presentation_result"):
                    result_obj = updates.get(result_key)
                    if result_obj and hasattr(result_obj, "execution_log"):
                        for log_entry in result_obj.execution_log:
                            await websocket.send_json({
                                "type":    "log",
                                "node":    node_name,
                                "content": log_entry,
                            })

                # Build compact node_complete summary (no full log)
                summary: dict = {}
                for result_key in ("cleaning_result", "analysis_result", "presentation_result"):
                    result_obj = updates.get(result_key)
                    if result_obj:
                        summary = _serialize_result(result_obj)

                # plan is a plain dict — extract steps directly
                if updates.get("plan"):
                    summary = {
                        "cleaning_steps": updates["plan"].get("cleaning_steps", []),
                        "analysis_steps": updates["plan"].get("analysis_steps", []),
                    }

                await websocket.send_json({
                    "type":    "node_complete",
                    "node":    node_name,
                    "summary": summary,
                })

        # ── HITL Checkpoint ───────────────────────────────────────────────────
        # graph.astream() exhausts when interrupt_before=["executive_presenter"]
        # halts execution. Confirm we're actually paused before proceeding.
        graph_state = graph.get_state(config)
        if "executive_presenter" not in (graph_state.next or []):
            session_store.update(session_id, {"status": "complete"})
            await websocket.send_json({"type": "pipeline_complete", "final_chart_paths": [], "executive_summary_md": ""})
            return

        # Pull draft charts + insights from the analyst result in the checkpoint
        analysis_result: AnalysisResult | None = graph_state.values.get("analysis_result")
        draft_chart_urls: list[str] = []
        insights: list[str] = []
        model_evaluations: list[dict] = []

        if analysis_result:
            draft_chart_urls = _chart_urls(analysis_result.draft_chart_paths)
            insights = analysis_result.insights
            model_evaluations = [me.model_dump() for me in analysis_result.model_evaluations]

        session_store.update(session_id, {"status": "hitl_paused"})
        await websocket.send_json({
            "type":              "hitl_pause",
            "charts":            draft_chart_urls,
            "insights":          insights,
            "model_evaluations": model_evaluations,
        })

        # ── Wait for HITL approval from client ────────────────────────────────
        raw = await websocket.receive_text()
        payload = json.loads(raw)
        action = payload.get("action")

        if action == "approve":
            graph.update_state(config, {"hitl_approved": True, "hitl_feedback": None})
        elif action == "revise":
            feedback = payload.get("feedback", "")
            graph.update_state(config, {"hitl_approved": True, "hitl_feedback": feedback})
        else:
            await websocket.send_json({
                "type":    "error",
                "message": f"Unknown HITL action '{action}'. Expected 'approve' or 'revise'.",
            })
            return

        session_store.update(session_id, {"status": "running"})

        # ── Phase 2: resume → executive_presenter ─────────────────────────────
        async for event in graph.astream(None, config=config, stream_mode="updates"):
            for node_name, updates in event.items():
                if node_name.startswith("__"):  # skip LangGraph internal signals
                    continue

                if node_name != current_node:
                    current_node = node_name
                    await websocket.send_json({
                        "type":         "node_start",
                        "node":         node_name,
                        "display_name": _NODE_DISPLAY.get(node_name, node_name),
                    })

                result_obj = updates.get("presentation_result")
                if result_obj and hasattr(result_obj, "execution_log"):
                    for log_entry in result_obj.execution_log:
                        await websocket.send_json({
                            "type":    "log",
                            "node":    node_name,
                            "content": log_entry,
                        })

                if result_obj:
                    summary = _serialize_result(result_obj)
                    summary["final_chart_paths"] = _chart_urls(result_obj.final_chart_paths)
                    await websocket.send_json({
                        "type":    "node_complete",
                        "node":    node_name,
                        "summary": summary,
                    })

        # ── Pipeline complete ─────────────────────────────────────────────────
        final_state = graph.get_state(config)
        pres_result: PresentationResult | None = final_state.values.get("presentation_result")

        session_store.update(session_id, {"status": "complete"})
        await websocket.send_json({
            "type":                 "pipeline_complete",
            "final_chart_paths":    _chart_urls(pres_result.final_chart_paths) if pres_result else [],
            "executive_summary_md": pres_result.executive_summary_md if pres_result else "",
        })

    except WebSocketDisconnect:
        session_store.update(session_id, {"status": "error"})

    except Exception as exc:
        session_store.update(session_id, {"status": "error"})
        try:
            await websocket.send_json({"type": "error", "message": str(exc)})
        except Exception:
            pass
