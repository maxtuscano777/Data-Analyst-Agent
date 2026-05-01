"""End-to-end integration test: all 4 ADAW agents in sequence.

Tests the complete pipeline:
    chief_planner_node → data_engineer_node
    → statistical_analyst_node → [simulated HITL] → executive_presenter_node

Nodes are invoked directly (not via graph.stream()) so the test runs without
the LangGraph checkpointer and without a WebSocket server. The HITL checkpoint
is simulated by setting state["hitl_approved"] = True before calling the
executive_presenter_node — exactly what the FastAPI HITL endpoint does in
production.

Run from project root:
    PYTHONPATH=. backend/.venv/bin/python3 test_pipeline_full.py

Expected runtime: 5–10 minutes (four live LLM + REPL stages).
"""

import json
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

# Load .env BEFORE importing any agent modules so GOOGLE_CLOUD_PROJECT,
# GOOGLE_CLOUD_REGION, and other env vars are available at import time.
load_dotenv(Path(__file__).parent / ".env")

from backend.api.data_profiler import generate_multi_file_profile
from backend.agents.chief_planner import chief_planner_node
from backend.agents.data_engineer import data_engineer_node
from backend.agents.statistical_analyst import statistical_analyst_node
from backend.agents.executive_presenter import executive_presenter_node

# ── Constants ──────────────────────────────────────────────────────────────────
SESSION_ID  = "olist-full-pipeline-test-001"
BACKEND_DIR = Path(__file__).parent / "backend"
LOGS_DIR    = BACKEND_DIR / "logs"
PLANS_DIR   = BACKEND_DIR / "plans"
RAW_DIR     = BACKEND_DIR / "uploads" / "raw"

USER_GOAL = (
    "Analyse revenue drivers and delivery performance. Identify which product "
    "categories and seller regions contribute most to revenue and late deliveries, "
    "and forecast order price using available features."
)

upload_paths = [
    str(RAW_DIR / "olist_orders_dataset.csv"),
    str(RAW_DIR / "olist_order_items_dataset.csv"),
    str(RAW_DIR / "olist_products_dataset.csv"),
]

# ── Step 0: Multi-file Data Profile (no LLM) ──────────────────────────────────
print("=" * 60)
print("STEP 0 — GENERATING DATA PROFILES")
print("=" * 60)
print("Profiling 3 Olist CSVs (pure pandas — no LLM)...\n")

profile = generate_multi_file_profile(upload_paths)

for filename, file_profile in profile.items():
    if "error" in file_profile:
        raise RuntimeError(f"Profiler error for {filename}: {file_profile['error']}")
    print(f"  {filename}: {file_profile['row_count']:,} rows × {len(file_profile['columns'])} cols")
    print(f"    columns: {file_profile['columns']}")
    nulls = {c: p for c, p in file_profile["null_pct"].items() if p > 0}
    if nulls:
        print("    null_pct (non-zero):")
        for col, pct in nulls.items():
            print(f"      {col}: {pct}%")

# ── Build AgentState ───────────────────────────────────────────────────────────
state = {
    "session_id":          SESSION_ID,
    "upload_paths":        upload_paths,
    "user_query":          USER_GOAL,
    "domain_context":      "Brazilian E-commerce logistics and sales",
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

# ── Step 1: Chief Planner ──────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("STEP 1 — CHIEF PLANNER")
print("=" * 60)
print("Calling chief_planner_node (live Gemini — may take 10-30s)...\n")

planner_result = chief_planner_node(state)
state.update(planner_result)
plan = state["plan"]

print("\nCLEANING STEPS:")
for i, step in enumerate(plan["cleaning_steps"], 1):
    print(f"  {i}. {step}")

print("\nANALYSIS STEPS:")
for i, step in enumerate(plan["analysis_steps"], 1):
    print(f"  {i}. {step}")

# ── Assertions: Chief Planner ──────────────────────────────────────────────────
assert isinstance(plan, dict), \
    "FAIL: plan is not a dict"
assert "cleaning_steps" in plan and len(plan["cleaning_steps"]) > 0, \
    "FAIL: plan missing non-empty 'cleaning_steps'"
assert "analysis_steps" in plan and len(plan["analysis_steps"]) > 0, \
    "FAIL: plan missing non-empty 'analysis_steps'"

plan_file = PLANS_DIR / f"{SESSION_ID}_plan.json"
assert plan_file.exists() and plan_file.stat().st_size > 0, \
    f"FAIL: plan JSON not found or empty at {plan_file}"

print(f"\n[OK] Planner: {len(plan['cleaning_steps'])} cleaning step(s), "
      f"{len(plan['analysis_steps'])} analysis step(s)")
print(f"[OK] plan JSON saved: {plan_file}")

# ── Step 2: Data Engineer ──────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("STEP 2 — DATA ENGINEER")
print("=" * 60)
print("Executing cleaning_steps via PythonAstREPLTool...")
print("(live Gemini + REPL — may take 60-180 seconds)\n")

engineer_result = data_engineer_node(state)
state.update(engineer_result)
cleaning_result = state["cleaning_result"]

cleaned_path = Path(cleaning_result.cleaned_csv_path)

# ── Assertions: Data Engineer ──────────────────────────────────────────────────
assert cleaned_path.exists(), \
    f"FAIL: cleaned CSV not found at {cleaned_path}"
assert cleaned_path.stat().st_size > 0, \
    f"FAIL: cleaned CSV is empty at {cleaned_path}"
assert cleaning_result.rows_after > 0, \
    "FAIL: rows_after is 0 — cleaning discarded all rows"

engineer_log = LOGS_DIR / f"{SESSION_ID}_engineer.log"
assert engineer_log.exists() and engineer_log.stat().st_size > 0, \
    f"FAIL: engineer log not found or empty at {engineer_log}"

# ── Print CleaningResult ───────────────────────────────────────────────────────
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

cleaned_df = pd.read_csv(cleaned_path)
print(f"\n  Verified CSV shape via pandas: {cleaned_df.shape}")

print(f"\n[OK] Engineer: cleaned CSV exists, {cleaning_result.rows_after:,} rows")
print(f"[OK] Engineer log: {engineer_log}")

# ── Step 3: Statistical Analyst ────────────────────────────────────────────────
print("\n" + "=" * 60)
print("STEP 3 — STATISTICAL ANALYST")
print("=" * 60)
print("Executing analysis_steps via PythonAstREPLTool...")
print("(live Gemini + REPL — may take 90-300 seconds)\n")

analyst_result = statistical_analyst_node(state)
state.update(analyst_result)
analysis_result = state["analysis_result"]

# ── Assertions: Statistical Analyst ───────────────────────────────────────────
analyst_log = LOGS_DIR / f"{SESSION_ID}_analyst.log"

assert analysis_result is not None, \
    "FAIL: analysis_result is None"
assert len(analysis_result.insights) > 0, \
    "FAIL: analysis_result.insights is empty"
assert isinstance(analysis_result.draft_chart_paths, list), \
    "FAIL: draft_chart_paths is not a list"
assert len(analysis_result.execution_log) > 0, (
    "FAIL: execution_log is empty — the model made no python_repl_ast calls.\n"
    "  Likely cause: LLM returned plain text on every turn despite reprompting.\n"
    f"  Check analyst log for [WARNING]/[DIAGNOSTIC] entries: {analyst_log}\n"
    "  Ensure GOOGLE_CLOUD_PROJECT and GOOGLE_CLOUD_REGION are set in .env."
)

assert analyst_log.exists(), \
    f"FAIL: analyst log not found at {analyst_log}"
assert analyst_log.stat().st_size > 0, (
    f"FAIL: analyst log exists but is empty (0 bytes) at {analyst_log}\n"
    "  This means the node exited before writing any log content."
)

# ── Print AnalysisResult ───────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("ANALYSIS RESULT")
print("=" * 60)

print("\n  INSIGHTS:")
for i, insight in enumerate(analysis_result.insights, 1):
    print(f"    {i}. {insight}")

print(f"\n  MODEL EVALUATIONS ({len(analysis_result.model_evaluations)}):")
if analysis_result.model_evaluations:
    for me in analysis_result.model_evaluations:
        tag = " [SELECTED]" if me.selected else ""
        print(f"    {me.model_name}: CV R² = {me.cv_r2_mean:.4f} ± {me.cv_r2_std:.4f}{tag}")
else:
    print("    (no model evaluations recorded)")

print(f"\n  DRAFT CHARTS ({len(analysis_result.draft_chart_paths)}):")
if analysis_result.draft_chart_paths:
    for p in analysis_result.draft_chart_paths:
        print(f"    {p}")
else:
    print("    (no draft charts saved)")

print(f"\n  execution_log entries: {len(analysis_result.execution_log)}")

print(f"\n[OK] Analyst: {len(analysis_result.insights)} insight(s), "
      f"{len(analysis_result.draft_chart_paths)} draft chart(s), "
      f"{len(analysis_result.model_evaluations)} model evaluation(s)")
print(f"[OK] Analyst log: {analyst_log}")

# ── HITL Checkpoint Simulation ─────────────────────────────────────────────────
print("\n" + "=" * 60)
print("HITL CHECKPOINT — HUMAN-IN-THE-LOOP REVIEW")
print("=" * 60)
print("In production, LangGraph pauses here with interrupt_before=['executive_presenter']")
print("and awaits a WebSocket approval signal from the React dashboard.")
print("")
print("Draft charts available for review:")
if analysis_result.draft_chart_paths:
    for p in analysis_result.draft_chart_paths:
        print(f"  - {p}")
else:
    print("  (no draft charts were generated)")
print("")
print("Simulating HITL approval: setting state['hitl_approved'] = True")
state["hitl_approved"] = True
print("[OK] HITL approved — proceeding to Executive Presenter.\n")

# ── Step 4: Executive Presenter ────────────────────────────────────────────────
print("\n" + "=" * 60)
print("STEP 4 — EXECUTIVE PRESENTER")
print("=" * 60)
print("Phase 1: Polishing charts via PythonAstREPLTool (Seaborn/Matplotlib)...")
print("Phase 2: Generating executive Markdown narrative via LLM (no REPL)...")
print("(may take 60-240 seconds)\n")

presenter_result = executive_presenter_node(state)
state.update(presenter_result)
presentation_result = state["presentation_result"]

# ── Assertions: Executive Presenter ───────────────────────────────────────────
assert presentation_result is not None, \
    "FAIL: presentation_result is None"
assert isinstance(presentation_result.executive_summary_md, str), \
    "FAIL: executive_summary_md is not a string"
assert len(presentation_result.executive_summary_md) > 0, \
    "FAIL: executive_summary_md is empty"
assert presentation_result.executive_summary_md.startswith("#"), (
    "FAIL: executive_summary_md does not start with '#'.\n"
    f"First 100 chars: {presentation_result.executive_summary_md[:100]!r}"
)
assert isinstance(presentation_result.execution_log, list), \
    "FAIL: presentation_result.execution_log is not a list"
assert isinstance(presentation_result.final_chart_paths, list), \
    "FAIL: final_chart_paths is not a list"

presenter_log = LOGS_DIR / f"{SESSION_ID}_presenter.log"
assert presenter_log.exists(), \
    f"FAIL: presenter log not found at {presenter_log}"

# ── Print PresentationResult ───────────────────────────────────────────────────
print("\n" + "=" * 60)
print("PRESENTATION RESULT")
print("=" * 60)

print(f"\n  FINAL CHARTS ({len(presentation_result.final_chart_paths)}):")
if presentation_result.final_chart_paths:
    for p in presentation_result.final_chart_paths:
        print(f"    {p}")
else:
    print("    (no final charts — draft charts used as fallback)")

print(f"\n  EXECUTIVE SUMMARY (first 500 chars):")
print("  " + "-" * 56)
preview = presentation_result.executive_summary_md[:500]
for line in preview.splitlines():
    print(f"  {line}")
if len(presentation_result.executive_summary_md) > 500:
    print("  ...")
print("  " + "-" * 56)

print(f"\n  executive_summary_md total length : "
      f"{len(presentation_result.executive_summary_md)} chars")
print(f"  execution_log entries             : "
      f"{len(presentation_result.execution_log)}")

print(f"\n[OK] Presenter: executive_summary_md starts with '#', "
      f"{len(presentation_result.final_chart_paths)} final chart(s)")
print(f"[OK] Presenter log: {presenter_log}")

# ── Final Summary ──────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("ALL PIPELINE STAGES PASSED")
print("=" * 60)

print("\nARTIFACT LOCATIONS:")
print(f"  plan JSON        → {PLANS_DIR / f'{SESSION_ID}_plan.json'}")
print(f"  cleaned CSV      → {cleaning_result.cleaned_csv_path}")
print(f"  engineer log     → {LOGS_DIR / f'{SESSION_ID}_engineer.log'}")
print(f"  analyst log      → {LOGS_DIR / f'{SESSION_ID}_analyst.log'}")
print(f"  presenter log    → {LOGS_DIR / f'{SESSION_ID}_presenter.log'}")
print(f"  draft charts dir → {BACKEND_DIR / 'charts' / 'draft' / SESSION_ID}")
print(f"  final charts dir → {BACKEND_DIR / 'charts' / 'final' / SESSION_ID}")

print(f"\nSTAGE SUMMARY:")
print(f"  Planner  : {len(plan['cleaning_steps'])} cleaning step(s), "
      f"{len(plan['analysis_steps'])} analysis step(s)")
print(f"  Engineer : {cleaning_result.rows_after:,} rows in cleaned CSV")
print(f"  Analyst  : {len(analysis_result.insights)} insight(s), "
      f"{len(analysis_result.draft_chart_paths)} draft chart(s), "
      f"{len(analysis_result.model_evaluations)} model evaluation(s)")
print(f"  Presenter: {len(presentation_result.final_chart_paths)} final chart(s), "
      f"{len(presentation_result.executive_summary_md):,} chars in executive summary")

print("\n" + "=" * 60)
