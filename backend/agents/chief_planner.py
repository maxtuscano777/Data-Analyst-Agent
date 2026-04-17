"""Agent 1 — The Chief Planner.

Responsibilities:
  - Receives the user's business goal and the compact Data Profile JSON.
  - Reasons about what cleaning and analysis steps are needed.
  - Outputs a strict, ordered ExecutionPlan (JSON) for downstream executor agents.

ABSOLUTE CONSTRAINTS:
  - NO tools. NO Python REPL. This agent never executes code.
  - NO access to the full CSV. It only sees the Data Profile summary.
  - Output is always validated against the ExecutionPlan Pydantic schema via
    .with_structured_output() — malformed responses are rejected at runtime.
"""

from __future__ import annotations

import json

from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI

from backend.schemas.output_schemas import AgentState, ExecutionPlan

# ── System prompt ──────────────────────────────────────────────────────────────
# Injected variables (via ChatPromptTemplate):
#   {user_query}    — the user's natural-language business goal
#   {data_profile}  — JSON string of the compact Data Profile
#
# Tone: Senior Data Scientist writing an execution plan, not writing code.

_SYSTEM_PROMPT = """\
You are a Senior Data Scientist acting as a Chief Planner for an autonomous \
data analysis pipeline. Your only job is to produce a precise, ordered \
execution plan — you do NOT write code, and you do NOT perform any analysis yourself.

You will be given:
  1. A business goal from the user.
  2. A Data Profile dict mapping each uploaded filename to its compact profile
     (column names, data types, null counts, null percentages, row count, and a 5-row sample).
     There may be one file or multiple files.

═══════════════════════════════════════════════════════
STEP 1 — FOREIGN KEY DETECTION (multi-file only)
═══════════════════════════════════════════════════════
If more than one file is present:
  a. Compare the column names of every pair of files.
  b. Any column that appears in two or more files with a compatible dtype
     (object / int64 / float64) is a CANDIDATE JOIN KEY.
  c. Typical FK patterns: "order_id", "product_id", "customer_id", "user_id", etc.

MERGE RULE — if join keys are found:
  Your FIRST cleaning_step MUST be a merge instruction. Use this exact format:
    "Load 'fileA.csv' into DataFrame fileA_stem and 'fileB.csv' into DataFrame fileB_stem.
     Merge fileA_stem with fileB_stem on '<key>' using an inner join, assign to df.
     Then merge df with fileC_stem (loaded from 'fileC.csv') on '<key2>' using a left join."
  - Specify the Python variable name as the file stem (no extension, no path).
  - Use inner join when both tables must have matching keys.
  - Use left join when the left table should retain all rows even if the right has no match.
  - Chain merges in logical order (fact table first, then dimension tables).

UNRELATED FILES RULE — if no shared columns exist:
  Instruct the Data Engineer to process each file independently and concatenate or
  report them separately. Do NOT force a merge where none is warranted.

═══════════════════════════════════════════════════════
STEP 2 — CLEANING STEPS (for the Data Engineer)
═══════════════════════════════════════════════════════
After the merge step (if any), list the remaining cleaning operations on the merged df:
  - Base decisions on null_pct and dtypes from the Data Profile.
  - Each step is a single, unambiguous instruction.
  - Good examples:
      "Strip leading/trailing whitespace from all string columns"
      "Parse the 'order_date' column as datetime64[ns]"
      "Fill missing values in 'weight_g' (numeric) with the column median"
      "Drop rows where 'delivery_date' is null"
      "Drop duplicate rows"
  - Do NOT include steps not warranted by the profiles.
  - Do NOT reference raw file paths in post-merge steps.

═══════════════════════════════════════════════════════
STEP 3 — ANALYSIS STEPS (for the Statistical Analyst)
═══════════════════════════════════════════════════════
  - Each step is a single, analytically precise instruction tied to the business goal.
  - Steps must be executable with Pandas, Scikit-learn, NumPy, Matplotlib, or Seaborn.
  - When a predictive model is appropriate, always specify:
      • The target column (inferred from the business goal and merged column names)
      • The algorithm(s): LinearRegression AND DecisionTreeRegressor
      • Evaluation MUST use cross_val_score(cv=5, scoring='r2'), not train/test split
  - Examples:
      "Compute and print the Pearson correlation matrix for all numeric columns"
      "Fit a LinearRegression and a DecisionTreeRegressor on target column 'price'; \
evaluate both with cross_val_score(cv=5, scoring='r2'); report mean ± std"
      "Generate a Seaborn heatmap of the correlation matrix; save as PNG"
  - Statistical rigor is mandatory: cross-validation reveals overfitting.

GLOBAL RULES:
  - Be specific and actionable. Vague instructions like "clean the data" are forbidden.
  - Do not invent columns that do not appear in the Data Profiles.
  - Produce between 3 and 8 cleaning steps (including the merge step if needed)
    and between 3 and 6 analysis steps.\
"""

_HUMAN_PROMPT = """\
BUSINESS GOAL:
{user_query}

UPLOADED FILES AND THEIR DATA PROFILES:
{data_profile}

Each top-level key is a filename. Analyze column names across all files to identify \
foreign keys. If files are joinable, your first cleaning_step MUST be the merge instruction \
(see format in system prompt).

Produce the ExecutionPlan now.\
"""

_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", _SYSTEM_PROMPT),
        ("human", _HUMAN_PROMPT),
    ]
)


# ── LangGraph node ─────────────────────────────────────────────────────────────

def chief_planner_node(state: AgentState) -> dict:
    """LangGraph node: generate an ExecutionPlan from the user goal + Data Profile.

    Reads from state:
        state["user_query"]   — user's natural-language business goal
        state["data_profile"] — compact dict produced by data_profiler.py
        state["llm_model"]    — Gemini model identifier (default: gemini-2.0-flash)

    Returns a partial state update:
        {"plan": {"cleaning_steps": [...], "analysis_steps": [...]}}
    """
    user_query: str = state.get("user_query") or "Perform a general exploratory data analysis."
    data_profile: dict = state.get("data_profile") or {}
    llm_model: str = state.get("llm_model") or "gemini-2.0-flash"

    # Serialize the Data Profile to a readable JSON string for the prompt.
    # Indented for readability — the LLM sees a tidy structure, not a blob.
    data_profile_str = json.dumps(data_profile, indent=2)

    llm = ChatGoogleGenerativeAI(
        model=llm_model,
        temperature=0,       # deterministic — plans should be stable
    )

    # Bind structured output — the LLM MUST return a valid ExecutionPlan.
    # Gemini supports function calling, which is what .with_structured_output uses.
    structured_llm = llm.with_structured_output(ExecutionPlan)

    chain = _prompt | structured_llm

    result: ExecutionPlan = chain.invoke(
        {
            "user_query": user_query,
            "data_profile": data_profile_str,
        }
    )

    return {"plan": result.model_dump()}
