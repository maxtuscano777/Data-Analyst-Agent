"""Agent 4 — The Executive Presenter.

Responsibilities:
  - Activated ONLY after the Human-in-the-Loop checkpoint is approved
    (hitl_approved=True, enforced by graph interrupt_before).
  - Phase 1 (REPL): Re-generates polished, board-ready Matplotlib/Seaborn charts
    from the cleaned data, using professional styling and annotations.
  - Phase 2 (LLM, no REPL): Writes a comprehensive executive Markdown narrative
    grounded in the analysis insights and model evaluations.
  - Returns final chart paths and the Markdown report via LangGraph state.

Two-phase design rationale:
  - REPL phase keeps chart generation deterministic and reproducible.
  - LLM narrative phase runs at temperature=0.3 for natural prose while
    remaining tightly grounded in the data-backed insights passed as context.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_experimental.tools import PythonAstREPLTool
from langchain_google_vertexai import ChatVertexAI

from backend.config import GCP_LOCATION, GCP_PROJECT
from backend.schemas.output_schemas import AgentState, AnalysisResult, PresentationResult

# ── Paths ──────────────────────────────────────────────────────────────────────
_FINAL_CHARTS_DIR = Path(__file__).parent.parent / "charts" / "final"

# ── Phase 1 prompts: chart polishing via REPL ──────────────────────────────────
_REPL_SYSTEM_PROMPT = """\
You are a Senior Data Visualization Engineer. You MUST use the python_repl_ast tool \
to execute ALL Python code. Your goal is polished, board-ready charts that would pass \
C-suite scrutiny.

RULES:
- The VERY FIRST python_repl_ast call must set the non-interactive backend:
    import matplotlib
    matplotlib.use('Agg')
- Apply sns.set_theme(style='whitegrid', palette='muted') in Block 1.
- SEABORN PALETTE RULE (Seaborn 0.13+): When passing `palette=` to any categorical
  plot function (barplot, boxplot, violinplot, stripplot, etc.), you MUST also pass
  `hue=` set to the same categorical variable and add `legend=False`. Omitting `hue=`
  while using `palette=` raises a FutureWarning and will break in a future release.
  Correct pattern:
    sns.barplot(data=df, x='category', y='value',
                hue='category', palette='muted', legend=False)
  For single-colour fills (no categorical split), use `color=` instead of `palette=`.
- Figure size: at least (10, 6) for presentation readability.
- Every chart must have: a clear title, labeled axes, and key annotations.
- Use plt.tight_layout() before plt.savefig().
- Call plt.close('all') after each savefig() to free memory.
- For correlation heatmaps: use a diverging colormap (center=0) and annotate cells.
- For model CV score charts: include error bars representing the std deviation.\
"""

# ── Phase 2 prompt: executive narrative (LLM only) ────────────────────────────
_NARRATIVE_SYSTEM_PROMPT = """\
You are a Senior Business Intelligence Analyst writing a board-ready executive report. \
Your audience is the C-suite: no jargon, data-backed, concise, and actionable.

Write a comprehensive Markdown executive summary with EXACTLY this structure:

# Executive Summary

## 1. Business Objective
(1–2 sentences describing the analytical question answered)

## 2. Data Overview
(2–3 bullets: dataset size, key tables joined, date range if applicable)

## 3. Key Findings
(4–6 bullets: the most important, quantified insights from the analysis)

## 4. Model Performance
(Include ONLY if models were evaluated. Summarize CV R² mean ± std per model.
 Explain what cross-validation reveals about real-world predictive power.
 Omit this section entirely if model_evaluations is empty.)

## 5. Recommendations
(3–5 actionable business recommendations grounded in the findings)

## 6. Methodology Note
(1–2 sentences on statistical methods used and why cross-validation matters)

FORMATTING RULES:
- Be specific and quantitative — cite actual numbers from the analysis.
- Use **bold** for key metrics.
- Do not hallucinate findings not supported by the provided insights.
- Omit Section 4 entirely if no predictive model was evaluated.\
"""


# ── ReAct loop tuning ─────────────────────────────────────────────────────────
_MAX_ITERATIONS = 20   # outer bound — sufficient for reprompts + chart blocks
_MAX_REPROMPTS  = 5    # consecutive plain-text turns before giving up

_NO_TOOL_CALL_REPROMPT = (
    "You MUST call python_repl_ast right now. Do NOT respond with plain text. "
    "Your next message must be a tool call. "
    "Execute Block 1 immediately: call python_repl_ast with the matplotlib backend, "
    "imports, and data-load statements shown in the human message above. "
    "No explanations — only a tool call."
)

_EMPTY_CONTENT_PLACEHOLDER = "[no content]"


def _coerce_nonempty_content(msgs: list) -> list:
    """Return a coerced copy of msgs where every message has non-empty content.

    Vertex AI rejects messages whose 'parts' field is empty or contains only
    empty strings. Replace empty content with a placeholder instead of removing
    the message, which would break the ReAct chain of thought.
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


def _build_repl_human(
    cleaned_csv_path: str,
    final_charts_dir: str,
    draft_chart_paths: list[str],
    insights: list[str],
    model_evaluations_json: str,
) -> str:
    """Build the REPL phase human prompt without .format() to avoid brace conflicts."""
    draft_list = "\n".join(f"  - {p}" for p in draft_chart_paths) or "  (no draft charts)"
    insights_list = "\n".join(f"  - {i}" for i in insights) or "  (no insights recorded)"
    return (
        "Produce polished, board-ready chart(s) from the cleaned data below.\n\n"
        f"CLEANED DATA FILE: {cleaned_csv_path}\n"
        f"DRAFT CHARTS (for context — do NOT copy these PNGs):\n{draft_list}\n"
        f"FINAL CHARTS DIRECTORY: {final_charts_dir}\n\n"
        f"ANALYSIS INSIGHTS TO VISUALIZE:\n{insights_list}\n\n"
        f"MODEL EVALUATIONS:\n{model_evaluations_json}\n\n"
        "REQUIRED SEQUENCE:\n\n"
        "BLOCK 1 — Set up environment (call python_repl_ast now with this exact code):\n"
        "import matplotlib\n"
        "matplotlib.use('Agg')\n"
        "import pandas as pd\n"
        "import numpy as np\n"
        "import matplotlib.pyplot as plt\n"
        "import seaborn as sns\n"
        "from pathlib import Path\n"
        "import os\n\n"
        "sns.set_theme(style='whitegrid', palette='muted')\n"
        f'os.makedirs(r"{final_charts_dir}", exist_ok=True)\n'
        f'df = pd.read_csv(r"{cleaned_csv_path}")\n'
        'print(f"Loaded {df.shape[0]} rows x {df.shape[1]} columns")\n\n'
        "BLOCK 2 — Regenerate each draft chart with polished styling:\n"
        "  - Recreate the visualization from cleaned data (do NOT copy the draft PNG).\n"
        "  - Apply professional Seaborn styling (whitegrid theme, muted palette).\n"
        "  - Add a descriptive title, axis labels, and key annotations.\n"
        f"  - Save each chart to: {final_charts_dir}/<descriptive_name>.png\n"
        "  - Print a confirmation after each savefig call.\n\n"
        "Call python_repl_ast now to execute Block 1."
    )


def _build_narrative_human(
    user_query: str,
    domain_context: str,
    insights: list[str],
    model_evaluations_json: str,
    summary_stats_snippet: str,
) -> str:
    """Build the narrative phase human prompt."""
    insights_list = "\n".join(f"- {i}" for i in insights) or "- (no insights recorded)"
    return (
        f"Business Goal: {user_query}\n"
        f"Domain: {domain_context}\n\n"
        f"Analysis Insights:\n{insights_list}\n\n"
        f"Model Evaluations:\n{model_evaluations_json}\n\n"
        f"Key Summary Statistics (top numeric columns):\n{summary_stats_snippet}\n\n"
        "Write the executive summary now."
    )


# ── LangGraph node ─────────────────────────────────────────────────────────────

def executive_presenter_node(state: AgentState, config: RunnableConfig = None) -> dict:
    """LangGraph node: generate final charts and executive Markdown summary.

    Must only execute after hitl_approved=True (enforced by graph interrupt_before).

    Reads from state:
        state["analysis_result"]    — AnalysisResult from Agent 3
        state["cleaning_result"]    — CleaningResult (for cleaned_csv_path)
        state["user_query"]         — business goal in natural language
        state["domain_context"]     — optional industry context
        state["llm_model"]          — Gemini model identifier
        state["session_id"]         — for scoped file paths and logs

    Returns a partial state update:
        {"presentation_result": PresentationResult(...)}
    """
    analysis_result: AnalysisResult | None = state.get("analysis_result")
    cleaning_result = state.get("cleaning_result")
    user_query: str = state.get("user_query") or "General exploratory data analysis"
    domain_context: str = state.get("domain_context") or "General Business"
    llm_model: str = state.get("llm_model") or "gemini-2.5-flash"
    session_id: str = state.get("session_id") or "unknown"

    cleaned_csv_path = (
        cleaning_result.cleaned_csv_path
        if cleaning_result
        else str(Path(__file__).parent.parent / "uploads" / "cleaned" / "cleaned_data.csv")
    )

    # Session-scoped final charts directory
    final_charts_dir = str(_FINAL_CHARTS_DIR / session_id)
    os.makedirs(final_charts_dir, exist_ok=True)

    # Unpack analysis results safely
    draft_chart_paths: list[str] = []
    insights: list[str] = []
    model_evaluations_data: list[dict] = []

    if analysis_result:
        draft_chart_paths = analysis_result.draft_chart_paths
        insights = analysis_result.insights
        model_evaluations_data = [
            me.model_dump() for me in analysis_result.model_evaluations
        ]

    model_evaluations_json = (
        json.dumps(model_evaluations_data, indent=2)
        if model_evaluations_data
        else "[]"
    )
    execution_log: list[str] = []

    # ── Phase 1: Polish charts via REPL ───────────────────────────────────────
    repl = PythonAstREPLTool()
    llm = ChatVertexAI(
        model=llm_model,
        project=GCP_PROJECT,
        location=GCP_LOCATION,
        temperature=0,
        max_retries=10,
    )
    llm_with_tools = llm.bind_tools([repl])

    repl_human = _build_repl_human(
        cleaned_csv_path=cleaned_csv_path,
        final_charts_dir=final_charts_dir,
        draft_chart_paths=draft_chart_paths,
        insights=insights,
        model_evaluations_json=model_evaluations_json,
    )
    conversation: list = [
        SystemMessage(content=_REPL_SYSTEM_PROMPT),
        HumanMessage(content=repl_human),
    ]

    tool_call_count = 0
    reprompt_count  = 0

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
            break  # done (tool_call_count > 0) or reprompts exhausted

        reprompt_count = 0  # reset streak — model is actively using the tool

        for tool_call in response.tool_calls:
            code_snippet = tool_call["args"].get("query", "")
            repl_output = repl.invoke({"query": code_snippet}, config=config) or "[Tool executed — no stdout]"
            tool_call_count += 1

            log_entry = (
                f"[TOOL: {tool_call['name']}]\n{code_snippet}\n[OUTPUT]\n{repl_output}"
            )
            execution_log.append(log_entry)
            conversation.append(
                ToolMessage(content=str(repl_output), tool_call_id=tool_call["id"])
            )

    # ── Phase 2: Executive narrative (LLM only, no REPL) ──────────────────────
    import pandas as _pd

    summary_stats_snippet = "(unavailable)"
    try:
        _df = _pd.read_csv(cleaned_csv_path)
        numeric_cols = _df.select_dtypes(include="number").columns[:5]
        summary_stats_snippet = _df[numeric_cols].describe().to_string()
    except Exception:
        pass

    narrative_human = _build_narrative_human(
        user_query=user_query,
        domain_context=domain_context,
        insights=insights,
        model_evaluations_json=model_evaluations_json,
        summary_stats_snippet=summary_stats_snippet,
    )

    # Slightly warmer temperature for natural prose, but still grounded (no hallucination)
    narrative_llm = ChatVertexAI(
        model=llm_model,
        project=GCP_PROJECT,
        location=GCP_LOCATION,
        temperature=0.3,
        max_retries=10,
    )
    narrative_response = narrative_llm.invoke([
        SystemMessage(content=_NARRATIVE_SYSTEM_PROMPT),
        HumanMessage(content=narrative_human),
    ])
    executive_summary_md: str = narrative_response.content

    # ── Collect final chart PNGs ───────────────────────────────────────────────
    final_chart_paths: list[str] = sorted(
        str(p) for p in Path(final_charts_dir).glob("*.png")
    )
    # Fallback: if REPL produced no charts, re-use draft charts from Agent 3
    if not final_chart_paths:
        final_chart_paths = draft_chart_paths

    # ── Persist execution log ──────────────────────────────────────────────────
    logs_dir = Path(__file__).parent.parent / "logs"
    os.makedirs(logs_dir, exist_ok=True)
    (logs_dir / f"{session_id}_presenter.log").write_text("\n\n".join(execution_log))

    presentation_result = PresentationResult(
        final_chart_paths=final_chart_paths,
        executive_summary_md=executive_summary_md,
        execution_log=execution_log,
    )
    return {"presentation_result": presentation_result}
