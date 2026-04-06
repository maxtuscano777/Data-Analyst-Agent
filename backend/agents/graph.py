"""LangGraph state machine for ADAW.

Graph topology:
  START → data_engineer → statistical_analyst → [HITL checkpoint] → executive_presenter → END

The graph compiles with ``interrupt_before=["executive_presenter"]`` so that
LangGraph pauses execution and awaits human approval before the final
presentation step.
"""

from __future__ import annotations

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

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

    # Register nodes
    builder.add_node("data_engineer", data_engineer_node)
    builder.add_node("statistical_analyst", statistical_analyst_node)
    builder.add_node("executive_presenter", executive_presenter_node)

    # Wire edges: linear pipeline
    builder.set_entry_point("data_engineer")
    builder.add_edge("data_engineer", "statistical_analyst")
    builder.add_edge("statistical_analyst", "executive_presenter")
    builder.add_edge("executive_presenter", END)

    # Compile with in-memory checkpointer and HITL interrupt
    checkpointer = MemorySaver()
    compiled = builder.compile(
        checkpointer=checkpointer,
        interrupt_before=["executive_presenter"],
    )
    return compiled


# Module-level singleton — import this in FastAPI route handlers
graph = build_graph()
