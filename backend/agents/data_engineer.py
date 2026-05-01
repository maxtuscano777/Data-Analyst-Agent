"""Agent 2 — The Data Engineer.

Responsibilities:
  - Reads `cleaning_steps` from the Chief Planner's ExecutionPlan.
  - Executes each step as Pandas code via PythonAstREPLTool (no autonomous planning).
  - Saves the cleaned DataFrame to backend/uploads/cleaned_data.csv.
  - Streams raw REPL output back via execution_log for WebSocket delivery.

ABSOLUTE CONSTRAINTS:
  - This agent is a DETERMINISTIC EXECUTOR — it does NOT invent cleaning steps.
  - All instructions come from state["plan"]["cleaning_steps"].
  - PythonAstREPLTool (AST-safe) is used instead of PythonREPLTool.
"""

from __future__ import annotations

import os
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_experimental.tools import PythonAstREPLTool
from langchain_google_vertexai import ChatVertexAI

from backend.schemas.output_schemas import AgentState, CleaningResult

# ── Paths ──────────────────────────────────────────────────────────────────────
_CLEANED_CSV_PATH = str(Path(__file__).parent.parent / "uploads" / "cleaned" / "cleaned_data.csv")

# ── Prompts ────────────────────────────────────────────────────────────────────
_SYSTEM_PROMPT = """\
You are a Senior Data Engineer. You MUST use the python_repl_ast tool to execute \
ALL Python code. Never write code in plain text — always call python_repl_ast. \
Use only pandas and the standard library. Do NOT perform any analysis or visualization.

CRITICAL PANDAS RULES (Pandas 2.x):
- NEVER use df[col].method(inplace=True) — it silently fails on copies.
- For fillna: use df[col] = df[col].fillna(value)  NOT  df[col].fillna(value, inplace=True)
- For dropna on rows: df.dropna(subset=[col], inplace=True) is fine (whole-DataFrame inplace).
- For drop_duplicates: df.drop_duplicates(inplace=True) is fine.
- For string ops: df[col] = df[col].str.strip()  NOT  df[col].str.strip(inplace=True)\
"""

_HUMAN_PROMPT_TEMPLATE = """\
Execute the following data-cleaning plan using the python_repl_ast tool.

AVAILABLE FILES (loaded as pandas DataFrames by their stem name in BLOCK 1):
{file_listing}
OUTPUT PATH: {output_path}

CLEANING STEPS (in order):
{steps_numbered}

REQUIRED SEQUENCE — use python_repl_ast for EACH block below:

BLOCK 1 — Load all datasets (call python_repl_ast now with this exact code):
import pandas as pd
{load_statements}
print("All files loaded.")

BLOCK 2 — Execute every cleaning step above, one python_repl_ast call per step. \
The first step is typically a merge — follow it exactly and assign the result to `df`. \
Print a one-line confirmation after each step (e.g. "Step 1 done").

BLOCK 3 — After all steps, save the cleaned DataFrame `df` (call python_repl_ast):
df.to_csv("{output_path}", index=False)
print("Saved.")

Call python_repl_ast now to execute Block 1.\
"""



def data_engineer_node(state: AgentState) -> dict:
    """LangGraph node: execute cleaning_steps via PythonAstREPLTool.

    Reads from state:
        state["upload_path"]       — path to the original CSV/Excel file
        state["plan"]["cleaning_steps"] — ordered list from Chief Planner
        state["llm_model"]         — Gemini model identifier
        state["data_profile"]      — compact profile (for rows_before fallback)

    Returns a partial state update:
        {
            "cleaning_result": CleaningResult(...),
            "messages": [<agent conversation turns>],
        }
    """
    upload_paths: list[str] = state.get("upload_paths") or []
    plan: dict = state.get("plan") or {}
    cleaning_steps: list[str] = plan.get("cleaning_steps", [])
    llm_model: str = state.get("llm_model") or "gemini-2.5-flash"
    data_profile: dict = state.get("data_profile") or {}

    # Sum row_counts across all profiled files as a rows_before approximation.
    rows_before_fallback: int = sum(
        v.get("row_count", 0) for v in data_profile.values() if isinstance(v, dict)
    )

    if not cleaning_steps:
        stub = CleaningResult(
            cleaned_csv_path=_CLEANED_CSV_PATH,
            rows_before=rows_before_fallback,
            rows_after=rows_before_fallback,
            columns_dropped=[],
            dtype_corrections={},
            execution_log=["[data_engineer] No cleaning steps found in plan — skipped."],
        )
        return {"cleaning_result": stub}

    # ── Build prompt variables ─────────────────────────────────────────────────
    steps_numbered = "\n".join(
        f"  {i + 1}. {step}" for i, step in enumerate(cleaning_steps)
    )
    # Variable name per file = stem without extension (matches Planner's instructions)
    load_statements = "\n".join(
        f'{Path(p).stem} = pd.read_csv("{p}")' for p in upload_paths
    )
    file_listing = "\n".join(
        f"  {Path(p).stem}  →  {p}" for p in upload_paths
    )
    human_content = _HUMAN_PROMPT_TEMPLATE.format(
        file_listing=file_listing,
        load_statements=load_statements,
        output_path=_CLEANED_CSV_PATH,
        steps_numbered=steps_numbered,
    )

    # ── Initialize REPL tool and LLM ──────────────────────────────────────────
    repl = PythonAstREPLTool()
    llm = ChatVertexAI(
        model=llm_model,
        project=os.getenv("GOOGLE_CLOUD_PROJECT", "project-38d33c02-d4a0-425d-a92"),
        location=os.getenv("GOOGLE_CLOUD_REGION", "us-central1"),
        temperature=0,
    )
    llm_with_tools = llm.bind_tools([repl])

    # ── Conversation seed ──────────────────────────────────────────────────────
    conversation: list = [
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(content=human_content),
    ]
    execution_log: list[str] = []

    # ── ReAct loop ─────────────────────────────────────────────────────────────
    max_iterations = 20  # guard against runaway loops
    for _ in range(max_iterations):
        response = llm_with_tools.invoke(conversation)
        conversation.append(response)

        # No tool calls → agent is done
        if not response.tool_calls:
            break

        for tool_call in response.tool_calls:
            code_snippet = tool_call["args"].get("query", "")
            repl_output = repl.invoke(code_snippet)

            log_entry = f"[TOOL: {tool_call['name']}]\n{code_snippet}\n[OUTPUT]\n{repl_output}"
            execution_log.append(log_entry)

            conversation.append(
                ToolMessage(
                    content=str(repl_output),
                    tool_call_id=tool_call["id"],
                )
            )

    # ── Post-process: read cleaned CSV directly for reliable metadata ──────────
    # Avoids dependence on REPL stdout capture (PythonAstREPLTool may truncate
    # large print output, so parsing REPL text is fragile).
    import os as _os
    import pandas as _pd  # local import — pandas is already installed in venv

    _os.makedirs(Path(_CLEANED_CSV_PATH).parent, exist_ok=True)
    cleaned_p = Path(_CLEANED_CSV_PATH)
    if cleaned_p.exists() and cleaned_p.stat().st_size > 0:
        cleaned_df = _pd.read_csv(cleaned_p)
        rows_after: int = len(cleaned_df)
        # Multi-file: no single orig_cols baseline — columns_dropped not meaningful here.
        columns_dropped: list[str] = []
        dtype_corrections: dict[str, str] = {
            col: str(cleaned_df[col].dtype) for col in cleaned_df.columns
        }
    else:
        rows_after = rows_before_fallback
        columns_dropped = []
        dtype_corrections = {}

    rows_before: int = rows_before_fallback

    # ── Persist execution log to backend/logs/{session_id}_engineer.log ───────
    session_id: str = state.get("session_id") or "unknown"
    logs_dir = Path(__file__).parent.parent / "logs"
    _os.makedirs(logs_dir, exist_ok=True)
    log_path = logs_dir / f"{session_id}_engineer.log"
    log_path.write_text("\n\n".join(execution_log))

    # ── Build CleaningResult ───────────────────────────────────────────────────
    cleaning_result = CleaningResult(
        cleaned_csv_path=_CLEANED_CSV_PATH,
        rows_before=rows_before,
        rows_after=rows_after,
        columns_dropped=columns_dropped,
        dtype_corrections=dtype_corrections,
        execution_log=execution_log,
    )

    return {
        "cleaning_result": cleaning_result,
        "messages": conversation[2:],  # exclude system + human seed; append agent turns
    }
