"""Agent 3 — The Executive Presenter.

Responsibilities:
  - Activated ONLY after the Human-in-the-Loop checkpoint is approved.
  - Generates polished, board-ready Matplotlib/Seaborn visualizations.
  - Writes a comprehensive executive narrative in Markdown.
  - Returns final chart paths and the Markdown report via LangGraph state.

This node is registered as the interrupt target in the LangGraph compiler:
  ``graph.compile(interrupt_before=["executive_presenter"])``
"""

from __future__ import annotations

from backend.agents.tools import get_python_repl
from backend.schemas.output_schemas import AgentState, PresentationResult


async def executive_presenter_node(state: AgentState) -> dict:
    """LangGraph node: generate final charts and executive summary.

    Args:
        state: Current shared AgentState (must have ``analysis_result`` and
               ``hitl_approved=True`` set).

    Returns:
        Partial state update dict with ``presentation_result`` populated.
    """
    # TODO Phase 2: implement full agent loop with LLM + REPL tool
    repl = get_python_repl()
    _ = repl  # will be used in Phase 2

    stub_result = PresentationResult(
        final_chart_paths=[],
        executive_summary_md="# Executive Summary\n\n_[stub] executive_presenter_node not yet implemented._",
        execution_log="[stub] executive_presenter_node not yet implemented.",
    )
    return {"presentation_result": stub_result}
