"""WebSocket handler for the ADAW pipeline.

Single channel per session: /ws/pipeline/{session_id}

Lifecycle:
  1. Client POSTs to /upload → receives session_id.
  2. Client opens ws://host/ws/pipeline/{session_id}.
  3. Server builds initial AgentState and calls graph.astream_events().
  4. Server emits events as they happen inside each node:
       node_start    → signals node has begun (client shows spinner)
       log           → individual tool call or output (streams in real-time)
       node_complete → compact summary of node output (client updates dashboard)
  5. graph.astream_events() exhausts when interrupt_before=["executive_presenter"].
  6. Server emits hitl_pause with draft chart URLs and analysis insights.
  7. Client sends {"action": "approve"} or {"action": "revise", "feedback": "..."}.
  8. Server resumes graph via graph.update_state() + graph.astream_events(None, ...).
  9. Server emits pipeline_complete with final chart URLs and executive Markdown.
 10. Logs and results are batch-persisted to SQLite after the WebSocket closes.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.api import sessions as session_store
from backend.agents.graph import graph
from backend.db import database as db
from backend.schemas.output_schemas import AnalysisResult, CleaningResult, PresentationResult

router = APIRouter()

_NODE_DISPLAY: dict[str, str] = {
    "chief_planner":       "Chief Planner",
    "data_engineer":       "Data Engineer",
    "statistical_analyst": "Statistical Analyst",
    "executive_presenter": "Executive Presenter",
}

# Set of node names to filter astream_events — avoids matching sub-chain events
_AGENT_NODES: frozenset[str] = frozenset(_NODE_DISPLAY.keys())

# Root of the charts directory — used to build relative /charts/... URLs
_CHARTS_ROOT = Path(__file__).parent.parent / "charts"


# ── Helpers ────────────────────────────────────────────────────────────────────

def _serialize_result(result: Any) -> dict:
    """Convert a Pydantic result model to a JSON-safe summary dict.

    execution_log is excluded — log entries are sent as individual WebSocket
    messages so the frontend can render them incrementally.
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


def _summary_from_output(output: dict) -> dict:
    """Extract a compact node_complete summary from an on_chain_end output dict."""
    for key in ("cleaning_result", "analysis_result", "presentation_result"):
        obj = output.get(key)
        if obj:
            return _serialize_result(obj)
    if output.get("plan"):
        plan = output["plan"]
        return {
            "cleaning_steps": plan.get("cleaning_steps", []),
            "analysis_steps": plan.get("analysis_steps", []),
        }
    return {}


def _chart_urls(chart_paths: list[str]) -> list[str]:
    """Convert absolute PNG paths to relative /charts/... HTTP URLs."""
    urls = []
    for p in chart_paths:
        try:
            rel = Path(p).relative_to(_CHARTS_ROOT)
            urls.append(f"/charts/{rel.as_posix()}")
        except ValueError:
            urls.append(p)
    return urls


def _extract_code(raw_input: Any) -> str:
    """Recursively hunt for a Python code string in on_tool_start input data.

    Handles all known LangGraph payload shapes:
      - bare string
      - {"query": "code"}  (standard PythonAstREPLTool schema)
      - {"input": {"query": "code"}}  (double-nested)
      - {"__arg1": "code"}  (positional arg encoding)
      - any other dict — falls back to first non-empty string value
    """
    if raw_input is None:
        return ""
    if isinstance(raw_input, str):
        return raw_input.strip()
    if isinstance(raw_input, dict):
        for key in ("query", "input", "code", "__arg1"):
            val = raw_input.get(key)
            if val:
                result = _extract_code(val)
                if result:
                    return result
        for val in raw_input.values():
            result = _extract_code(val)
            if result:
                return result
    return ""


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

    # ── Accumulators — populated during streaming, persisted at completion ──────
    accumulated_logs:  list[dict] = []
    accumulated_nodes: dict[str, dict] = {}

    # ── Inner helpers: send + accumulate in one call ───────────────────────────
    async def _log(node: str | None, content: str) -> None:
        await websocket.send_json({"type": "log", "node": node, "content": content})
        accumulated_logs.append({"node": node, "content": content})

    async def _complete(node: str, summary: dict) -> None:
        await websocket.send_json({"type": "node_complete", "node": node, "summary": summary})
        accumulated_nodes[node] = {
            "node_name": node,
            "status":    "complete",
            "summary":   json.dumps(summary),
        }

    try:
        # ── Phase 1: chief_planner → data_engineer → statistical_analyst ──────
        current_node: str | None = None

        async for event in graph.astream_events(initial_state, config=config, version="v2"):
            kind = event["event"]
            name = event.get("name", "")
            data = event.get("data", {})

            # Node begins — emit node_start once per node
            if kind == "on_chain_start" and name in _AGENT_NODES and name != current_node:
                current_node = name
                await websocket.send_json({
                    "type":         "node_start",
                    "node":         name,
                    "display_name": _NODE_DISPLAY[name],
                })

            # REPL tool starting — extract and emit the code being executed
            elif kind == "on_tool_start" and name == "python_repl_ast":
                code = _extract_code(data.get("input"))
                if code:
                    await _log(current_node, f"[TOOL: python_repl_ast]\n{code}")

            # REPL tool finished — emit stdout output
            elif kind == "on_tool_end" and name == "python_repl_ast":
                output = str(data.get("output", "") or "[no output]")
                await _log(current_node, f"[OUTPUT]\n{output}")

            # Node finished — emit compact summary
            elif kind == "on_chain_end" and name in _AGENT_NODES:
                summary = _summary_from_output(data.get("output") or {})
                await _complete(name, summary)

        # ── HITL Checkpoint ───────────────────────────────────────────────────
        # astream_events exhausts when interrupt_before=["executive_presenter"] fires.
        graph_state = graph.get_state(config)
        if "executive_presenter" not in (graph_state.next or []):
            session_store.update(session_id, {"status": "complete"})
            await websocket.send_json({"type": "pipeline_complete", "final_chart_paths": [], "executive_summary_md": ""})
            await websocket.close(1000)
            try:
                await db.update_session(session_id, status="complete", final_chart_paths="[]", executive_summary_md="")
                await db.save_logs(session_id, accumulated_logs)
                await db.save_nodes(session_id, list(accumulated_nodes.values()))
            except Exception:
                pass
            return

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
        async for event in graph.astream_events(None, config=config, version="v2"):
            kind = event["event"]
            name = event.get("name", "")
            data = event.get("data", {})

            if kind == "on_chain_start" and name in _AGENT_NODES and name != current_node:
                current_node = name
                await websocket.send_json({
                    "type":         "node_start",
                    "node":         name,
                    "display_name": _NODE_DISPLAY[name],
                })

            elif kind == "on_tool_start" and name == "python_repl_ast":
                code = _extract_code(data.get("input"))
                if code:
                    await _log(current_node, f"[TOOL: python_repl_ast]\n{code}")

            elif kind == "on_tool_end" and name == "python_repl_ast":
                output = str(data.get("output", "") or "[no output]")
                await _log(current_node, f"[OUTPUT]\n{output}")

            elif kind == "on_chain_end" and name in _AGENT_NODES:
                summary = _summary_from_output(data.get("output") or {})
                # Remap final chart paths to HTTP URLs for the presenter
                pres = (data.get("output") or {}).get("presentation_result")
                if pres:
                    summary["final_chart_paths"] = _chart_urls(pres.final_chart_paths)
                await _complete(name, summary)

        # ── Pipeline complete ─────────────────────────────────────────────────
        final_state = graph.get_state(config)
        pres_result: PresentationResult | None = final_state.values.get("presentation_result")

        final_chart_paths_http = _chart_urls(pres_result.final_chart_paths) if pres_result else []
        exec_summary_md = pres_result.executive_summary_md if pres_result else ""

        session_store.update(session_id, {"status": "complete"})
        await websocket.send_json({
            "type":                 "pipeline_complete",
            "final_chart_paths":    final_chart_paths_http,
            "executive_summary_md": exec_summary_md,
        })
        await websocket.close(1000)

        # Persist to DB after WebSocket close — failure here is non-critical
        try:
            await db.update_session(
                session_id,
                status="complete",
                final_chart_paths=json.dumps(final_chart_paths_http),
                executive_summary_md=exec_summary_md,
            )
            await db.save_logs(session_id, accumulated_logs)
            await db.save_nodes(session_id, list(accumulated_nodes.values()))
        except Exception:
            pass

    except WebSocketDisconnect:
        session_store.update(session_id, {"status": "error"})

    except Exception as exc:
        session_store.update(session_id, {"status": "error"})
        try:
            await websocket.send_json({"type": "error", "message": str(exc)})
        except Exception:
            pass
        try:
            await db.update_session(session_id, status="error")
        except Exception:
            pass
