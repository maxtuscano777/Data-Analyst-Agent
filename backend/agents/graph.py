"""LangGraph state machine for ADAW.

Graph topology:
  START → chief_planner → data_engineer → statistical_analyst
        → [HITL checkpoint] → executive_presenter → END

The graph compiles with ``interrupt_before=["executive_presenter"]`` so that
LangGraph pauses execution and awaits human approval before the final
presentation step.

HITL resume pattern (from FastAPI route handler):
    graph.update_state(config, {"hitl_approved": True})
    graph.stream(None, config=config)
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


def build_graph() -> StateGraph:
    """Construct and compile the ADAW LangGraph workflow.

    Returns:
        A compiled LangGraph ``StateGraph`` with HITL checkpoint enabled.
    """
    builder = StateGraph(AgentState)

    # Register all four agent nodes
    builder.add_node("chief_planner", chief_planner_node)
    builder.add_node("data_engineer", data_engineer_node)
    builder.add_node("statistical_analyst", statistical_analyst_node)
    builder.add_node("executive_presenter", executive_presenter_node)

    # Wire edges: linear pipeline — planner → engineer → analyst → [HITL] → presenter
    builder.set_entry_point("chief_planner")
    builder.add_edge("chief_planner", "data_engineer")
    builder.add_edge("data_engineer", "statistical_analyst")
    builder.add_edge("statistical_analyst", "executive_presenter")
    builder.add_edge("executive_presenter", END)

    # Compile with in-memory checkpointer and HITL interrupt before final step
    checkpointer = MemorySaver(serde=JsonPlusSerializer())
    compiled = builder.compile(
        checkpointer=checkpointer,
        interrupt_before=["executive_presenter"],
    )
    return compiled


# Module-level singleton — import this in FastAPI route handlers
graph = build_graph()
