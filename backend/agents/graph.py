"""LangGraph state machine for ADAW.

Graph topology:
  START → chief_planner → data_engineer → statistical_analyst
        → hitl_router → [HITL checkpoint]
              ├── (hitl_feedback set)   → chief_planner  (revision cycle)
              └── (hitl_feedback clear) → executive_presenter → END

The graph compiles with ``interrupt_before=["hitl_router"]`` so that
LangGraph pauses *before* the sentinel node runs. When resumed, the sentinel
executes (returning {}), and the conditional edge ``_route_after_hitl``
re-evaluates the current state to route either forward (approve) or back to
the planner (revise). This prevents LangGraph from locking in the routing
decision at checkpoint time — the key fix for the HITL bypass bug.

HITL resume pattern (from FastAPI route handler):
    graph.update_state(config, {"hitl_approved": True, "hitl_feedback": None})
    graph.astream_events(None, config=config)   # approve → executive_presenter

    graph.update_state(config, {"hitl_approved": True, "hitl_feedback": "..."})
    graph.astream_events(None, config=config)   # revise  → chief_planner → loop
"""

from __future__ import annotations

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from backend.agents.chief_planner import chief_planner_node
from backend.agents.data_engineer import data_engineer_node
from backend.agents.statistical_analyst import statistical_analyst_node
from backend.agents.executive_presenter import executive_presenter_node
from backend.schemas.output_schemas import AgentState


def hitl_router_node(state: AgentState) -> dict:
    """Sentinel node that sits at the HITL breakpoint.

    Returns an empty dict (no state mutations). Its only job is to exist so
    that ``interrupt_before=["hitl_router"]`` fires here — before the
    conditional edge below decides where to route.
    """
    return {}


def _route_after_hitl(state: AgentState) -> str:
    """Conditional edge: route based on what the human decided at the HITL pause.

    Called after hitl_router_node runs (i.e. after the graph resumes from the
    interrupt). Reads the state that was injected via graph.update_state():
      - hitl_feedback set   → route back to chief_planner for revision
      - hitl_feedback clear → proceed to executive_presenter
    """
    return "chief_planner" if state.get("hitl_feedback") else "executive_presenter"


def build_graph() -> StateGraph:
    """Construct and compile the ADAW LangGraph workflow.

    Returns:
        A compiled LangGraph ``StateGraph`` with HITL checkpoint enabled.
    """
    builder = StateGraph(AgentState)

    # Register all agent nodes (including the HITL sentinel)
    builder.add_node("chief_planner", chief_planner_node)
    builder.add_node("data_engineer", data_engineer_node)
    builder.add_node("statistical_analyst", statistical_analyst_node)
    builder.add_node("hitl_router", hitl_router_node)
    builder.add_node("executive_presenter", executive_presenter_node)

    # Wire edges: planner → engineer → analyst → hitl_router → (conditional) → presenter/planner
    builder.set_entry_point("chief_planner")
    builder.add_edge("chief_planner", "data_engineer")
    builder.add_edge("data_engineer", "statistical_analyst")
    builder.add_edge("statistical_analyst", "hitl_router")
    builder.add_conditional_edges(
        "hitl_router",
        _route_after_hitl,
        {"chief_planner": "chief_planner", "executive_presenter": "executive_presenter"},
    )
    builder.add_edge("executive_presenter", END)

    # interrupt_before the sentinel — routing decision is deferred until after resume
    checkpointer = MemorySaver(serde=JsonPlusSerializer())
    compiled = builder.compile(
        checkpointer=checkpointer,
        interrupt_before=["hitl_router"],
    )
    return compiled


# Module-level singleton — import this in FastAPI route handlers
graph = build_graph()
