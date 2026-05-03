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
# _CLEANED_CSV_PATH is computed per-session inside data_engineer_node to prevent
# data corruption when multiple sessions run concurrently.

# ── ReAct loop tuning ─────────────────────────────────────────────────────────
_MAX_ITERATIONS = 20   # outer bound — enough for 5 reprompts + ~6 cleaning steps
_MAX_REPROMPTS  = 5    # consecutive plain-text turns before giving up

# Injected when the model returns plain text before making its first tool call.
_NO_TOOL_CALL_REPROMPT = (
    "You MUST call python_repl_ast right now. Do NOT respond with plain text. "
    "Your next message must be a tool call. "
    "Execute Block 1 immediately: call python_repl_ast with the import and "
    "CSV load statements shown in the human message above. No explanations — only a tool call."
)

# ── Vertex AI empty-content guard ──────────────────────────────────────────────
_EMPTY_CONTENT_PLACEHOLDER = "[no content]"


def _coerce_nonempty_content(msgs: list) -> list:
    """Return a coerced copy of msgs where every message has non-empty content.

    Vertex AI rejects messages whose 'parts' field is empty or contains only
    empty strings. We replace empty content with a placeholder instead of
    removing the message, which would break the ReAct chain of thought.
    Uses Pydantic's model_copy() — the original message objects are never mutated.
    """
    result = []
    for msg in msgs:
        content = msg.content
        is_empty = (
            (isinstance(content, str) and not content.strip())
            or (
                isinstance(content, list)
                and not any(
                    (isinstance(item, str) and item.strip())
                    or (isinstance(item, dict) and item.get("text", "").strip())
                    for item in content
                )
            )
        )
        result.append(
            msg.model_copy(update={"content": _EMPTY_CONTENT_PLACEHOLDER})
            if is_empty
            else msg
        )
    return result

# ── Prompts ────────────────────────────────────────────────────────────────────
_SYSTEM_PROMPT = """\
You are a Senior Data Engineer. You MUST use the python_repl_ast tool to execute \
ALL Python code. Never write code in plain text — always call python_repl_ast. \
Use only pandas and the standard library. Do NOT perform any analysis or visualization.

CRITICAL PANDAS RULES — Pandas 2.x Copy-on-Write (CoW) is ENFORCED:

RULE 1 — COLUMN-LEVEL inplace IS BANNED. df['col'] returns a CoW copy. ANY
inplace method on it writes to the copy and raises ChainedAssignmentError.
  WRONG:  df['col'].fillna(value, inplace=True)
  WRONG:  df['col'].replace(old, new, inplace=True)
  WRONG:  df['col'].astype(dtype)  [without assignment — this does nothing]
  RIGHT:  df['col'] = df['col'].fillna(value)
  RIGHT:  df['col'] = df['col'].replace(old, new)
  RIGHT:  df['col'] = df['col'].astype(dtype)

RULE 2 — CHAINED BOOLEAN INDEXING IS BANNED. df[mask]['col'] = value writes
to a temporary copy — the original df is never updated.
  WRONG:  df[df['col'] > 0]['col'] = 1
  RIGHT:  df.loc[df['col'] > 0, 'col'] = 1
  Use df.loc[mask, col] = value for ALL conditional column mutations.

RULE 3 — DATETIME PARSING. ALWAYS use pd.to_datetime with errors='coerce'.
  RIGHT:  df['col'] = pd.to_datetime(df['col'], errors='coerce')
  WRONG:  df['col'].replace('', pd.NaT, inplace=True)
  WRONG:  df['col'] = df['col'].astype('datetime64[ns]')   # raises on bad values
  Parse ALL datetime columns with a single direct assignment — no inplace, no replace.

SAFE WHOLE-DATAFRAME inplace (these are fine — operate on df itself, not a copy):
  df.dropna(subset=[col], inplace=True)
  df.drop_duplicates(inplace=True)
  df.drop(columns=[col], inplace=True)
  df.rename(columns={...}, inplace=True)
  df.reset_index(drop=True, inplace=True)\
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
    session_id: str = state.get("session_id") or "default"

    # Session-scoped cleaned CSV path — prevents data corruption across concurrent sessions.
    _cleaned_csv_path = str(
        Path(__file__).parent.parent / "uploads" / "cleaned" / session_id / "cleaned_data.csv"
    )

    # Sum row_counts across all profiled files as a rows_before approximation.
    rows_before_fallback: int = sum(
        v.get("row_count", 0) for v in data_profile.values() if isinstance(v, dict)
    )

    if not cleaning_steps:
        stub = CleaningResult(
            cleaned_csv_path=_cleaned_csv_path,
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
        output_path=_cleaned_csv_path,
        steps_numbered=steps_numbered,
    )

    # ── Initialize REPL tool and LLM ──────────────────────────────────────────
    repl = PythonAstREPLTool()
    llm = ChatVertexAI(
        model=llm_model,
        project="advisorai-62611",
        location="us-central1",
        temperature=0,
        max_retries=10,
    )
    llm_with_tools = llm.bind_tools([repl])

    # ── Conversation seed ──────────────────────────────────────────────────────
    conversation: list = [
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(content=human_content),
    ]
    execution_log: list[str] = []
    tool_call_count = 0   # total REPL executions across all loop iterations
    reprompt_count  = 0   # consecutive plain-text turns before first tool call

    # ── ReAct loop ─────────────────────────────────────────────────────────────
    for _ in range(_MAX_ITERATIONS):
        response = llm_with_tools.invoke(_coerce_nonempty_content(conversation))
        conversation.append(response)

        if not response.tool_calls:
            if tool_call_count == 0 and reprompt_count < _MAX_REPROMPTS:
                reprompt_count += 1
                execution_log.append(
                    f"[WARNING] No tool call on turn {reprompt_count} — "
                    f"injecting reprompt ({reprompt_count}/{_MAX_REPROMPTS})."
                )
                conversation.append(HumanMessage(content=_NO_TOOL_CALL_REPROMPT))
                continue
            # Either done (tool_call_count > 0) or reprompts exhausted.
            break

        reprompt_count = 0  # reset streak — model is actively using the tool

        for tool_call in response.tool_calls:
            code_snippet = tool_call["args"].get("query", "")
            repl_output = repl.invoke(code_snippet) or "[Tool executed — no stdout]"
            tool_call_count += 1

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

    _os.makedirs(Path(_cleaned_csv_path).parent, exist_ok=True)
    cleaned_p = Path(_cleaned_csv_path)
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
    logs_dir = Path(__file__).parent.parent / "logs"
    _os.makedirs(logs_dir, exist_ok=True)
    log_path = logs_dir / f"{session_id}_engineer.log"
    log_path.write_text("\n\n".join(execution_log))

    # ── Build CleaningResult ───────────────────────────────────────────────────
    cleaning_result = CleaningResult(
        cleaned_csv_path=_cleaned_csv_path,
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
