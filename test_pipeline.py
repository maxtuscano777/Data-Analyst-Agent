"""Integration test: multi-file Planner → Engineer pipeline.

Passes 3 raw Olist CSVs directly into state["upload_paths"].
The Chief Planner autonomously detects the foreign keys (order_id, product_id)
and instructs the Data Engineer to merge them — no hardcoded pd.merge() here.

Run from project root:
    PYTHONPATH=. backend/.venv/bin/python3 test_pipeline.py
"""

import json
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from backend.api.data_profiler import generate_multi_file_profile
from backend.agents.chief_planner import chief_planner_node
from backend.agents.data_engineer import data_engineer_node

UPLOADS = Path(__file__).parent / "backend" / "uploads"

USER_GOAL = (
    "I want to understand if shipping costs (freight_value) are impacting our "
    "sales volume and if certain product categories are more affected by delivery "
    "delays than others."
)

upload_paths = [
    str(UPLOADS / "olist_orders_dataset.csv"),
    str(UPLOADS / "olist_order_items_dataset.csv"),
    str(UPLOADS / "olist_products_dataset.csv"),
]

# ── 1. Multi-file Profile ──────────────────────────────────────────────────────
print("Generating multi-file Data Profiles...")
profile = generate_multi_file_profile(upload_paths)

for filename, file_profile in profile.items():
    if "error" in file_profile:
        raise RuntimeError(f"Profiler error for {filename}: {file_profile['error']}")
    print(f"\n  {filename}: {file_profile['row_count']:,} rows × {len(file_profile['columns'])} cols")
    print(f"    columns: {file_profile['columns']}")
    nulls = {c: p for c, p in file_profile["null_pct"].items() if p > 0}
    if nulls:
        print("    null_pct (non-zero):")
        for col, pct in nulls.items():
            print(f"      {col}: {pct}%")

# ── 2. Build AgentState ────────────────────────────────────────────────────────
state = {
    "session_id":          "olist-pipeline-test-002",
    "upload_paths":        upload_paths,
    "user_query":          USER_GOAL,
    "data_profile":        profile,
    "plan":                None,
    "llm_model":           "gemini-2.5-flash",
    "hitl_approved":       False,
    "hitl_feedback":       None,
    "messages":            [],
    "cleaning_result":     None,
    "analysis_result":     None,
    "presentation_result": None,
}

# ── 3. Chief Planner ───────────────────────────────────────────────────────────
print("\nCalling Chief Planner (live Gemini API — gemini-2.5-flash)...")
print("(Planner must autonomously detect order_id / product_id FK joins)\n")

planner_result = chief_planner_node(state)
state.update(planner_result)
plan = state["plan"]

print("\n" + "=" * 60)
print("CHIEF PLANNER — EXECUTION PLAN")
print("=" * 60)

print("\nCLEANING STEPS:")
for i, step in enumerate(plan["cleaning_steps"], 1):
    print(f"  {i}. {step}")

print("\nANALYSIS STEPS:")
for i, step in enumerate(plan["analysis_steps"], 1):
    print(f"  {i}. {step}")

# ── 4. Verify the Planner detected the joins ───────────────────────────────────
first_step = plan["cleaning_steps"][0].lower()
assert "merge" in first_step or "join" in first_step, (
    f"FAIL: cleaning_steps[0] is not a merge/join instruction:\n  {plan['cleaning_steps'][0]}"
)
print("\n[OK] cleaning_steps[0] is a merge/join instruction — FK detection succeeded.")

# ── 5. Data Engineer ───────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("DATA ENGINEER — EXECUTING CLEANING STEPS")
print("=" * 60)
print("(live Gemini + PythonAstREPLTool — this may take 30-120 seconds)\n")

engineer_result = data_engineer_node(state)
state.update(engineer_result)

cleaning_result = state["cleaning_result"]

# ── 6. Verify cleaned CSV ──────────────────────────────────────────────────────
cleaned_path = Path(cleaning_result.cleaned_csv_path)
assert cleaned_path.exists(), f"FAIL: {cleaned_path} not found on disk"
assert cleaned_path.stat().st_size > 0, f"FAIL: {cleaned_path} is empty"

# ── 7. Print CleaningResult ────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("CLEANING RESULT")
print("=" * 60)

rows_dropped = cleaning_result.rows_before - cleaning_result.rows_after
print(f"  cleaned_csv_path : {cleaning_result.cleaned_csv_path}")
print(f"  rows_before      : {cleaning_result.rows_before:,}  (sum of all input files)")
print(f"  rows_after       : {cleaning_result.rows_after:,}")
print(f"  rows_dropped     : {rows_dropped:,}")

dtype_items = list(cleaning_result.dtype_corrections.items())
print(f"\n  dtype_corrections ({len(dtype_items)} cols — first 10):")
for col, dtype in dtype_items[:10]:
    print(f"    {col}: {dtype}")

log = cleaning_result.execution_log
print(f"\n  execution_log entries: {len(log)}")
for entry in log[:2]:
    preview = entry[:400] + "..." if len(entry) > 400 else entry
    print(f"\n  --- LOG ENTRY ---\n{preview}")

cleaned_df = pd.read_csv(cleaned_path)
print(f"\n  Verified cleaned CSV shape: {cleaned_df.shape}")

print("\n" + "=" * 60)
print("PIPELINE TEST PASSED")
print("=" * 60)
print(f"  cleaned_data.csv → {cleaned_path}")
print(f"  No hardcoded pd.merge() — joins were detected and executed by the agents.")
