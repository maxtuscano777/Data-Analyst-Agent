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
  2. A compact Data Profile of their dataset (column names, data types, \
null counts, null percentages, row count, and a 5-row sample).

Using ONLY this information, produce an ExecutionPlan with two ordered lists:

CLEANING STEPS (for the Data Engineer):
  - Each step is a single, unambiguous data-cleaning instruction.
  - Base your decisions on the null_pct and dtypes in the Data Profile.
  - Examples of good steps:
      "Drop columns where null percentage exceeds 50%"
      "Parse the 'order_date' column as datetime64[ns]"
      "Fill missing values in 'age' (numeric) with the column median"
      "Strip leading/trailing whitespace from all string columns"
      "Drop duplicate rows"
  - Do NOT include steps that are not warranted by the Data Profile.

ANALYSIS STEPS (for the Statistical Analyst):
  - Each step is a single, analytically precise instruction tied to the business goal.
  - Steps must be executable with Pandas, Scikit-learn, NumPy, Matplotlib, or Seaborn.
  - When a predictive model is appropriate, always specify:
      • The target column (inferred from the business goal and column names)
      • The algorithm(s) to try (e.g. LinearRegression AND DecisionTreeRegressor)
      • That evaluation MUST use cross_val_score(cv=5, scoring='r2'), not a simple train/test split
  - Examples of good steps:
      "Compute and print the Pearson correlation matrix for all numeric columns"
      "Plot a histogram for each numeric column; save each as a PNG to the charts directory"
      "Fit a LinearRegression and a DecisionTreeRegressor on target column 'revenue'; \
evaluate both using cross_val_score(cv=5, scoring='r2'); report mean ± std for each"
      "Generate a Seaborn heatmap of the correlation matrix; save as PNG"
  - Statistical rigor is mandatory: never claim zero bias for an unconstrained \
DecisionTreeRegressor — cross-validation results will reveal overfitting.

RULES:
  - Be specific and actionable. Vague instructions like "clean the data" are forbidden.
  - Order steps logically (cleaning before analysis, drop before impute, etc.).
  - Do not invent columns that do not appear in the Data Profile.
  - Do not reference the raw file path or filenames in your steps.
  - Produce between 3 and 8 cleaning steps and between 3 and 6 analysis steps.\
"""

_HUMAN_PROMPT = """\
BUSINESS GOAL:
{user_query}

DATA PROFILE:
{data_profile}

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
