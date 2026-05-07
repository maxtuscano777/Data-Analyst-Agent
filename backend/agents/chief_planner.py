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
import os
from pathlib import Path

from langchain_core.prompts import ChatPromptTemplate
from langchain_google_vertexai import ChatVertexAI

from backend.config import GCP_LOCATION, GCP_PROJECT
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
    "Merge `olist_orders_dataset` with `olist_order_items_dataset` on 'order_id' using
     an inner join, assign to df. Then merge df with `olist_products_dataset` on
     'product_id' using a left join."
  - VARIABLE NAME RULE: The Python variable name for each file is the filename WITHOUT
    its extension and WITHOUT any suffix. Examples: 'orders.csv' → `orders`,
    'olist_orders_dataset.csv' → `olist_orders_dataset`. NEVER append "_stem",
    "_df", or any other suffix. The Data Engineer loads each file using exactly
    this variable name.
  - Use inner join when both tables must have matching keys.
  - Use left join when the left table should retain all rows even if the right has no match.
  - Chain merges in logical order (fact table first, then dimension tables).
  - SUFFIX RULE: If two tables being merged share any non-key column names, Pandas will
    auto-append '_x' and '_y' suffixes. After the merge step, you MUST add an explicit
    cleaning step to either (a) drop the redundant '_x' or '_y' column, or (b) rename
    it to the correct intended name. Reference the exact column names with their suffix
    (e.g. "Drop column 'price_y'; rename 'price_x' to 'price'").
  - POST-JOIN CARDINALITY REASONING: Real-world joins can cause massive row explosions.
    You must think critically about the relationship between tables (1-to-1, 1-to-many,
    many-to-many, etc.). Instruct the Engineer to print the post-merge row count.
    If an unintended explosion is likely, do NOT blindly drop duplicates. Instead, devise
    a logically sound strategy based on the Business Goal (e.g., aggregate metrics on the
    'many' table BEFORE joining, or adjust the join keys) to preserve data integrity.

UNRELATED FILES RULE — if no shared columns exist:
  Instruct the Data Engineer to process each file independently and concatenate or
  report them separately. Do NOT force a merge where none is warranted.

═══════════════════════════════════════════════════════
STEP 2 — CLEANING STEPS (for the Data Engineer)
═══════════════════════════════════════════════════════
List the remaining cleaning operations on the working DataFrame(s):
  - If a merge occurred in step 1, all subsequent steps operate on the merged `df`.
  - If files are unrelated (no merge), each step must explicitly name which DataFrame
    it targets (e.g. "On the `orders` DataFrame, drop rows where 'status' is null").
  - Base decisions on null_pct, dtypes, and unique_values_count from the Data Profile.
  - Each step is a single, unambiguous instruction.
  - Good examples:
      "Strip leading/trailing whitespace from all string columns in df"
      "Parse the 'order_date' column in df as datetime64[ns]"
      "Fill missing values in 'weight_g' in df with the column median"
      "Drop rows in df where 'delivery_date' is null"
      "Drop duplicate rows in df"
  - Do NOT include steps not warranted by the profiles.
  - Do NOT reference raw file paths in post-merge steps.

  NULL HANDLING RULE (CRITICAL):
  NEVER drop rows based on null values if those rows contain valid data for OTHER parts
  of the analysis. For example, an order missing a delivery date still has valid 'price'
  and 'freight_value' data — do NOT drop it during cleaning.
  Instead, leave nulls intact. Instruct the Statistical Analyst to handle NaNs locally
  (e.g., using dropna(subset=[...])) ONLY when performing the specific calculation or
  chart that requires that column.

═══════════════════════════════════════════════════════
STEP 3 — ANALYSIS STEPS (for the Statistical Analyst)
═══════════════════════════════════════════════════════
  - Each step is a single, analytically precise instruction tied to the business goal.
  - Steps must be executable with Pandas, Scikit-learn, NumPy, Matplotlib, or Seaborn.
  - When a predictive model is appropriate, always specify:
      • The target column (inferred from the business goal and merged column names)
      • The algorithm(s): LinearRegression AND DecisionTreeRegressor
      • Evaluation MUST use cross_val_score(cv=5, scoring='r2'), not train/test split
  - ML DATA PREP RULE (mandatory when a model is requested):
      All feature columns passed to `.fit()` MUST be numeric. Before any model-fitting
      step, you MUST instruct the Analyst to prepare the feature matrix:
        • Apply One-Hot Encoding (`pd.get_dummies()`) to low-cardinality categorical
          columns (i.e. where `unique_values_count` is less than 20) that are
          analytically relevant (e.g. 'product_category_name').
        • OR explicitly drop all remaining object-dtype columns from the feature matrix.
      Never pass a DataFrame containing string/object columns directly to a sklearn estimator.
  - Examples:
      "Compute and print the Pearson correlation matrix for all numeric columns"
      "Apply pd.get_dummies() to 'product_category_name'; drop all remaining object-dtype \
columns; fit a LinearRegression and a DecisionTreeRegressor on target column 'price'; \
evaluate both with cross_val_score(cv=5, scoring='r2'); report the mean and standard deviation"
      "Generate a Seaborn heatmap of the correlation matrix; save as PNG"
  - Statistical rigor is mandatory: cross-validation reveals overfitting.

  VISUALIZATION RULE (MANDATORY):
  At least ONE analysis step MUST instruct the Statistical Analyst to generate and
  save a chart as a PNG file. The chart must be:
    - Directly tied to a key finding from the analysis (not a generic placeholder).
    - Produced with Seaborn or Matplotlib.
    - Named descriptively (e.g. top_revenue_categories.png, delivery_delay_dist.png).
  Choose the chart type that best fits the data and business goal:
    • Bar chart     — ranked categorical comparisons (top N categories, seller rankings)
    • Distribution  — numeric column spread (price, freight_value, delivery_days)
    • Scatter plot  — relationship between two numeric variables
    • Heatmap       — correlation matrix across numeric features
  The Analyst's system prompt handles saving mechanics (tight_layout, savefig, close).
  This chart is what the human reviewer sees at the HITL checkpoint. Without it, the
  HITL stage has no visuals to display and the Executive Presenter has nothing to polish.

GLOBAL RULES:
  - Be specific and actionable. Vague instructions like "clean the data" are forbidden.
  - Do not invent columns that do not appear in the Data Profiles.
  - Produce up to 8 necessary cleaning steps and up to 6 high-value analysis steps.
    Do not invent steps just to fill a quota — only include steps justified by the
    Data Profile and the Business Goal.\
"""

_HUMAN_PROMPT = """\
{domain_section}

BUSINESS GOAL:
{user_query}

{feedback_section}

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
    llm_model: str = state.get("llm_model") or "gemini-2.5-flash"
    domain_context: str | None = state.get("domain_context")
    hitl_feedback: str | None = state.get("hitl_feedback")

    # Serialize the Data Profile to a readable JSON string for the prompt.
    # Indented for readability — the LLM sees a tidy structure, not a blob.
    data_profile_str = json.dumps(data_profile, indent=2)

    # Build optional sections — empty string when not provided (renders as blank line).
    domain_section = f"DOMAIN CONTEXT:\n{domain_context}" if domain_context else ""
    feedback_section = (
        f"HUMAN FEEDBACK ON PREVIOUS PLAN:\n{hitl_feedback}\n"
        "You MUST adjust your plan to satisfy this feedback."
        if hitl_feedback else ""
    )

    llm = ChatVertexAI(
        model=llm_model,
        project=GCP_PROJECT,
        location=GCP_LOCATION,
        temperature=0,       # deterministic — plans should be stable
        max_retries=10,
    )

    # Bind structured output — the LLM MUST return a valid ExecutionPlan.
    # Gemini supports function calling, which is what .with_structured_output uses.
    structured_llm = llm.with_structured_output(ExecutionPlan)

    chain = _prompt | structured_llm

    result: ExecutionPlan = chain.invoke(
        {
            "user_query":       user_query,
            "data_profile":     data_profile_str,
            "domain_section":   domain_section,
            "feedback_section": feedback_section,
        }
    )

    # ── Persist plan to backend/plans/{session_id}_plan.json ──────────────────
    session_id: str = state.get("session_id") or "unknown"
    plans_dir = Path(__file__).parent.parent / "plans"
    os.makedirs(plans_dir, exist_ok=True)
    plan_path = plans_dir / f"{session_id}_plan.json"
    plan_path.write_text(json.dumps(result.model_dump(), indent=2))

    return {"plan": result.model_dump()}
