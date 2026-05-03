"""Agent 3 — The Statistical Analyst.

Responsibilities:
  - Reads `analysis_steps` from the Chief Planner's ExecutionPlan.
  - Executes each step sequentially via PythonAstREPLTool.
  - Maintains strict statistical rigor: cross-validation is REQUIRED for all models.
  - Saves draft charts as PNG for the HITL review checkpoint.
  - Parses an ANALYSIS_SUMMARY block from REPL output to extract insights and
    model evaluations into structured Pydantic types.
  - Streams raw REPL output back via LangGraph state.

Statistical Rigor Constraint (from project spec):
  Models must be evaluated with cross_val_score(cv=5). An unconstrained
  DecisionTreeRegressor has zero training bias but potentially HIGH variance —
  overfitting is detected and reported via cross-validation std deviation.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from google.api_core.exceptions import InvalidArgument
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_experimental.tools import PythonAstREPLTool
from langchain_google_vertexai import ChatVertexAI

from backend.schemas.output_schemas import AgentState, AnalysisResult, ModelEvaluation

# ── Paths ──────────────────────────────────────────────────────────────────────
_DRAFT_CHARTS_DIR = Path(__file__).parent.parent / "charts" / "draft"

# ── ReAct loop tuning ─────────────────────────────────────────────────────────
_MAX_ITERATIONS = 30   # outer bound — enough for 3 reprompts + ~6 analysis steps
_MAX_REPROMPTS  = 5    # consecutive plain-text turns before giving up

# Injected when the model returns plain text before making its first tool call.
_NO_TOOL_CALL_REPROMPT = (
    "You MUST call python_repl_ast right now. Do NOT respond with plain text. "
    "Your next message must be a tool call. "
    "Execute Block 1 immediately: call python_repl_ast with the imports and "
    "CSV load code shown in the human message above. No explanations — only a tool call."
)

# ── System prompt ──────────────────────────────────────────────────────────────
# {draft_charts_dir} is the only placeholder — formatted at node invocation.
# Double-braces {{ }} in the JSON example render to single braces after .format().
_SYSTEM_PROMPT_TEMPLATE = """\
You are a Senior Statistical Analyst. You MUST use the python_repl_ast tool to \
execute ALL Python code. Never write code in plain text — always call python_repl_ast.
Use pandas, numpy, scikit-learn, matplotlib, and seaborn only.

STATISTICAL RIGOR RULES (MANDATORY):
- Cross-validation (cv=5) is REQUIRED for every predictive model.
  Use: cross_val_score(estimator, X, y, cv=5, scoring='r2')
- An unconstrained DecisionTreeRegressor has zero training bias but HIGH variance.
  Always report both mean AND standard deviation of CV scores.
- NEVER claim a model is unbiased without empirical cross-validation evidence.
- Handle NaN values locally per analysis step using dropna(subset=[...]) — do NOT
  drop rows globally, as other valid data in those rows must be preserved.

CHART RULES:
- The VERY FIRST python_repl_ast call (Block 1) must set the non-interactive backend:
    import matplotlib
    matplotlib.use('Agg')
- Save every chart to: {draft_charts_dir}
- Use plt.tight_layout() before plt.savefig().
- Call plt.close('all') after each savefig() to free memory.
- Name chart files descriptively (e.g. correlation_heatmap.png, cv_scores.png).
- SEABORN PALETTE RULE (Seaborn 0.13+): When passing `palette=` to any categorical
  plot function (barplot, boxplot, violinplot, stripplot, etc.), you MUST also pass
  `hue=` set to the same categorical variable and add `legend=False`. Omitting `hue=`
  while using `palette=` raises a FutureWarning and will break in a future release.
  Correct pattern:
    sns.barplot(data=df, x='category', y='value',
                hue='category', palette='muted', legend=False)
  For single-colour fills (no categorical split), use `color=` instead of `palette=`.

PANDAS SAFETY RULES — Pandas 2.x Copy-on-Write (CoW) is ENFORCED:

RULE — COLUMN-LEVEL inplace IS BANNED. df['col'] or df_copy['col'] returns a CoW
copy in Pandas 2.x. ANY inplace call on it raises ChainedAssignmentError and the
original DataFrame is never updated.

The most common violation in ML feature prep is the median imputation loop:
  WRONG:
    for col in cols:
        df[col].fillna(df[col].median(), inplace=True)   # ChainedAssignmentError
  RIGHT (direct assignment per column):
    for col in cols:
        df[col] = df[col].fillna(df[col].median())
  RIGHT (vectorized — one line):
    df[cols] = df[cols].fillna(df[cols].median())

General rule: NEVER use inplace=True on a column expression. ALWAYS assign back:
  df['col'] = df['col'].fillna(value)
  df['col'] = df['col'].replace(old, new)
  df['col'] = df['col'].astype(dtype)

SAFE whole-DataFrame inplace (these operate on df itself, not a copy):
  df.drop(columns=[col], inplace=True)
  df.drop_duplicates(inplace=True)
  df.rename(columns={{...}}, inplace=True)

SUMMARY RULE (MANDATORY — the very last python_repl_ast call):
After completing all analysis steps, make one final python_repl_ast call whose ONLY
statement is a single print() call that outputs the entire summary block in one shot:

summary = {{
    "insights": [
        "<data-backed finding 1>",
        "<data-backed finding 2>",
        "<data-backed finding 3>"
    ],
    "model_evaluations": [
        {{"model_name": "<name>", "cv_r2_mean": <float>, "cv_r2_std": <float>, "selected": <bool>}},
    ]
}}
print("---ANALYSIS_SUMMARY---\\n" + json.dumps(summary, indent=2) + "\\n---END_SUMMARY---")

CRITICAL RULES for the summary call:
- The print() must be the ONLY statement in the final code block (not preceded by any
  other print, assignment inside the same block, etc. — build the dict first in a
  SEPARATE prior tool call if needed, then the last call is ONLY this one print()).
- Use a single print() with string concatenation as shown — NOT three separate print()
  calls. Three separate prints only capture the last one.
- The ---END_SUMMARY--- marker is REQUIRED on its own line inside the print string.
- If no predictive model was fitted, set "model_evaluations" to [].
- Insights must be 3–5 quantified, data-backed findings (cite actual numbers).\
"""


def _build_human_content(
    cleaned_csv_path: str,
    draft_charts_dir: str,
    steps_numbered: str,
) -> str:
    """Build the human-turn prompt as a plain string (avoids .format() brace conflicts)."""
    return (
        "Execute the following statistical analysis plan using python_repl_ast.\n\n"
        f"CLEANED DATA FILE: {cleaned_csv_path}\n"
        f"DRAFT CHARTS DIRECTORY: {draft_charts_dir}\n\n"
        f"ANALYSIS STEPS (in order):\n{steps_numbered}\n\n"
        "REQUIRED SEQUENCE:\n\n"
        "BLOCK 1 — Set up environment and load data (call python_repl_ast now with this exact code):\n"
        "import matplotlib\n"
        "matplotlib.use('Agg')\n"
        "import pandas as pd\n"
        "import numpy as np\n"
        "import matplotlib.pyplot as plt\n"
        "import seaborn as sns\n"
        "from sklearn.linear_model import LinearRegression\n"
        "from sklearn.tree import DecisionTreeRegressor\n"
        "from sklearn.model_selection import cross_val_score\n"
        "from pathlib import Path\n"
        "import os, json\n\n"
        f'os.makedirs(r"{draft_charts_dir}", exist_ok=True)\n'
        f'df = pd.read_csv(r"{cleaned_csv_path}")\n'
        'print(f"Loaded {df.shape[0]} rows x {df.shape[1]} columns")\n'
        "print(df.dtypes.to_string())\n\n"
        "BLOCK 2 — Execute every analysis step above, one python_repl_ast call per step.\n"
        f"When saving charts, always save to: {draft_charts_dir}/<descriptive_name>.png\n"
        "Print a one-line confirmation after each step (e.g. 'Step 1 done').\n\n"
        "BLOCK 3 — Final Summary (the last mandatory python_repl_ast call):\n"
        "This call must contain ONLY ONE statement: a single print() that outputs the\n"
        "entire summary block in one shot. Use this exact pattern:\n\n"
        "  summary = {\n"
        '      "insights": ["<finding 1>", "<finding 2>", "<finding 3>"],\n'
        '      "model_evaluations": [\n'
        '          {"model_name": "<n>", "cv_r2_mean": 0.0, "cv_r2_std": 0.0, "selected": True}\n'
        "      ]\n"
        "  }\n"
        '  print("---ANALYSIS_SUMMARY---\\n" + json.dumps(summary, indent=2) + "\\n---END_SUMMARY---")\n\n'
        "Do NOT use three separate print() calls — only the last print is captured.\n"
        "Build the summary dict in a prior tool call if needed; this final call prints only.\n\n"
        "Call python_repl_ast now to execute Block 1."
    )


_EMPTY_CONTENT_PLACEHOLDER = "[no content]"


def _coerce_nonempty_content(msgs: list[BaseMessage]) -> list[BaseMessage]:
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


def _extract_summary_json(log: str) -> dict | None:
    """Extract the JSON object from ---ANALYSIS_SUMMARY--- in REPL [OUTPUT] sections.

    PythonAstREPLTool only captures the stdout of the LAST statement in a code block.
    This means the marker can appear in two places in the log:
      - Inside a code block (in a print() call string) — must be IGNORED
      - Inside an [OUTPUT] block — the actual captured REPL output — VALID

    We distinguish the two by checking whether the nearest preceding section tag
    ([OUTPUT] vs [TOOL:]) before the marker. Only [OUTPUT]-section markers are parsed.
    Brace-depth counting then finds the complete outer JSON object boundary without
    requiring ---END_SUMMARY--- to be present.
    """
    marker = "---ANALYSIS_SUMMARY---"
    output_tag = "[OUTPUT]"
    tool_tag = "[TOOL:"

    search_pos = 0
    while True:
        marker_pos = log.find(marker, search_pos)
        if marker_pos == -1:
            return None

        preceding = log[:marker_pos]
        last_output = preceding.rfind(output_tag)
        last_tool = preceding.rfind(tool_tag)

        if last_output <= last_tool:
            # Marker is inside a code block — skip and continue searching.
            search_pos = marker_pos + 1
            continue

        # Marker is inside an [OUTPUT] block — extract the JSON.
        start = log.find("{", marker_pos + len(marker))
        if start == -1:
            return None

        depth = 0
        for i, ch in enumerate(log[start:], start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(log[start : i + 1])
                    except (json.JSONDecodeError, ValueError):
                        return None
        return None


# ── LangGraph node ─────────────────────────────────────────────────────────────

def statistical_analyst_node(state: AgentState) -> dict:
    """LangGraph node: execute analysis_steps via PythonAstREPLTool.

    Reads from state:
        state["cleaning_result"]            — CleaningResult (provides cleaned_csv_path)
        state["plan"]["analysis_steps"]     — ordered list from Chief Planner
        state["llm_model"]                  — Gemini model identifier
        state["session_id"]                 — for log and chart path scoping

    Returns a partial state update:
        {
            "analysis_result": AnalysisResult(...),
            "messages": [<agent conversation turns>],
        }
    """
    time.sleep(20)  # quota pacing: let data_engineer's TPM usage age out before starting
    cleaning_result = state.get("cleaning_result")
    plan: dict = state.get("plan") or {}
    analysis_steps: list[str] = plan.get("analysis_steps", [])
    llm_model: str = state.get("llm_model") or "gemini-2.5-flash"
    session_id: str = state.get("session_id") or "unknown"

    cleaned_csv_path = (
        cleaning_result.cleaned_csv_path
        if cleaning_result
        else str(Path(__file__).parent.parent / "uploads" / "cleaned" / "cleaned_data.csv")
    )

    # Session-scoped draft charts directory
    draft_charts_dir = str(_DRAFT_CHARTS_DIR / session_id)
    os.makedirs(draft_charts_dir, exist_ok=True)

    if not analysis_steps:
        return {
            "analysis_result": AnalysisResult(
                summary_statistics={},
                insights=["No analysis steps found in plan — skipped."],
                model_evaluations=[],
                draft_chart_paths=[],
                execution_log=["[statistical_analyst] No analysis steps in plan."],
            )
        }

    # ── Build prompts ──────────────────────────────────────────────────────────
    steps_numbered = "\n".join(
        f"  {i + 1}. {step}" for i, step in enumerate(analysis_steps)
    )
    system_content = _SYSTEM_PROMPT_TEMPLATE.format(draft_charts_dir=draft_charts_dir)
    human_content = _build_human_content(cleaned_csv_path, draft_charts_dir, steps_numbered)

    # ── Initialize REPL and LLM ────────────────────────────────────────────────
    repl = PythonAstREPLTool()
    llm = ChatVertexAI(
        model=llm_model,
        project="advisorai-62611",
        location="us-central1",
        temperature=0,
        max_retries=10,
    )
    llm_with_tools = llm.bind_tools([repl])

    seed_conversation: list[BaseMessage] = [
        SystemMessage(content=system_content),
        HumanMessage(content=human_content),
    ]
    conversation: list[BaseMessage] = list(seed_conversation)
    execution_log: list[str] = []
    tool_call_count = 0   # total REPL executions across all loop iterations
    reprompt_count  = 0   # consecutive plain-text turns with no tool calls

    # ── ReAct loop ─────────────────────────────────────────────────────────────
    for _ in range(_MAX_ITERATIONS):
        try:
            response = llm_with_tools.invoke(_coerce_nonempty_content(conversation))
        except InvalidArgument as exc:
            execution_log.append(f"[ERROR] Vertex InvalidArgument — aborting loop: {exc}")
            break
        conversation.append(response)

        if not response.tool_calls:
            if tool_call_count == 0 and reprompt_count < _MAX_REPROMPTS:
                # Model has never used the tool — inject a strict reprompt and retry.
                reprompt_count += 1
                execution_log.append(
                    f"[WARNING] No tool call on turn {reprompt_count} — "
                    f"injecting reprompt ({reprompt_count}/{_MAX_REPROMPTS})."
                )
                conversation.append(HumanMessage(content=_NO_TOOL_CALL_REPROMPT))
                continue
            # Either the agent is done (tool_call_count > 0) or reprompts exhausted.
            break

        reprompt_count = 0  # reset streak — model is actively using the tool

        for tool_call in response.tool_calls:
            code_snippet = tool_call["args"].get("query", "").strip()

            if not code_snippet:
                # Malformed tool call — log a warning and return an empty ToolMessage
                # so the conversation stays structurally valid for the next LLM turn.
                execution_log.append(
                    f"[WARNING] Tool call '{tool_call['name']}' had an empty "
                    f"'query' argument — skipped."
                )
                conversation.append(
                    ToolMessage(
                        content="[WARNING: empty code snippet — nothing executed]",
                        tool_call_id=tool_call["id"],
                    )
                )
                continue

            repl_output = repl.invoke(code_snippet) or "[Tool executed — no stdout]"
            tool_call_count += 1

            log_entry = (
                f"[TOOL: {tool_call['name']}]\n{code_snippet}\n[OUTPUT]\n{repl_output}"
            )
            execution_log.append(log_entry)

            conversation.append(
                ToolMessage(content=str(repl_output), tool_call_id=tool_call["id"])
            )

    # ── Diagnostic fallback when no REPL call ever fired ──────────────────────
    if tool_call_count == 0:
        execution_log.append(
            f"[DIAGNOSTIC] No python_repl_ast calls were made after "
            f"{_MAX_REPROMPTS} reprompt attempts. The model consistently "
            "returned plain text. Analysis could not be executed. "
            "Check that the LLM model supports tool/function calling and "
            "that GOOGLE_CLOUD_PROJECT / GOOGLE_CLOUD_REGION are set correctly."
        )

    # ── Parse ---ANALYSIS_SUMMARY--- block from REPL output ───────────────────
    insights: list[str] = []
    model_evaluations: list[ModelEvaluation] = []

    full_log = "\n".join(execution_log)
    summary_data = _extract_summary_json(full_log)
    if summary_data:
        try:
            insights = summary_data.get("insights", [])
            raw_evals: list[dict] = summary_data.get("model_evaluations", [])
            if raw_evals:
                best_mean = max(float(e.get("cv_r2_mean", -999.0)) for e in raw_evals)
                model_evaluations = [
                    ModelEvaluation(
                        model_name=e["model_name"],
                        cv_r2_mean=float(e["cv_r2_mean"]),
                        cv_r2_std=float(e["cv_r2_std"]),
                        selected=(float(e.get("cv_r2_mean", -999.0)) == best_mean),
                    )
                    for e in raw_evals
                ]
        except (KeyError, TypeError, ValueError):
            insights = ["Analysis completed — see execution log for detailed results."]

    # ── Summary statistics (direct pandas read — avoids REPL truncation) ──────
    import pandas as _pd

    summary_statistics: dict = {}
    try:
        _df = _pd.read_csv(cleaned_csv_path)
        summary_statistics = (
            _df.describe(include="all").fillna("").astype(str).to_dict()
        )
    except Exception:
        pass

    # ── Collect draft chart PNGs from session directory ────────────────────────
    draft_chart_paths: list[str] = sorted(
        str(p) for p in Path(draft_charts_dir).glob("*.png")
    )

    # ── Persist execution log ──────────────────────────────────────────────────
    logs_dir = Path(__file__).parent.parent / "logs"
    os.makedirs(logs_dir, exist_ok=True)
    (logs_dir / f"{session_id}_analyst.log").write_text("\n\n".join(execution_log))

    # ── Build AnalysisResult ───────────────────────────────────────────────────
    if not insights:
        if tool_call_count == 0:
            insights = [
                "[Diagnostic] REPL execution failed — model did not call python_repl_ast "
                "after reprompting. See analyst log for details."
            ]
        else:
            insights = ["Analysis completed — see execution log for detailed results."]

    analysis_result = AnalysisResult(
        summary_statistics=summary_statistics,
        insights=insights,
        model_evaluations=model_evaluations,
        draft_chart_paths=draft_chart_paths,
        execution_log=execution_log,
    )
    start_idx = 2 if len(conversation) >= 2 else 0
    return {
        "analysis_result": analysis_result,
        "messages": conversation[start_idx:],  # exclude seed prompt pair when present
    }
