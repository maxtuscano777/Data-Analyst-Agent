"""Agent 1 — The Data Engineer.

Responsibilities:
  - Automatically writes and executes Python/Pandas code to clean structured data.
  - Handles missing values, type corrections, empty column drops, formatting.
  - Streams raw REPL output back via LangGraph state for WebSocket delivery.
"""

from __future__ import annotations

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

from backend.agents.tools import get_python_repl
from backend.schemas.output_schemas import AgentState, CleaningResult

_SYSTEM_PROMPT = """You are a meticulous Data Engineer. Your only job is to clean the
uploaded dataset and return a cleaned CSV file. You must:
1. Load the file from the provided path using Pandas.
2. Drop columns that are entirely empty.
3. Infer and correct data types (dates, numerics, booleans).
4. Fill or drop rows with missing values using the most appropriate strategy.
5. Save the cleaned file to the same directory with a '_cleaned' suffix.
6. Report the before/after row counts, dropped columns, and dtype corrections.
Do NOT perform any analysis or visualization.
"""


async def data_engineer_node(state: AgentState) -> dict:
    """LangGraph node: clean the uploaded dataset.

    Args:
        state: Current shared AgentState.

    Returns:
        Partial state update dict with ``cleaning_result`` populated.
    """
    # TODO Phase 2: implement full agent loop with LLM + REPL tool
    # Placeholder — returns a minimal stub result so the graph can be wired up.
    repl = get_python_repl()
    _ = repl  # will be used in Phase 2

    stub_result = CleaningResult(
        cleaned_csv_path=state.upload_path,
        rows_before=0,
        rows_after=0,
        columns_dropped=[],
        dtype_corrections={},
        execution_log="[stub] data_engineer_node not yet implemented.",
    )
    return {"cleaning_result": stub_result}
