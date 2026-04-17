"""End-to-end test: 3-way Olist merge → data_profiler → chief_planner_node.

Run from project root:
    PYTHONPATH=. backend/.venv/bin/python3 test_planner.py
"""

import json
import os
import tempfile
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from backend.api.data_profiler import generate_data_profile
from backend.agents.chief_planner import chief_planner_node

UPLOADS = Path(__file__).parent / "backend" / "uploads"
ORDERS_PATH   = UPLOADS / "olist_orders_dataset.csv"
ITEMS_PATH    = UPLOADS / "olist_order_items_dataset.csv"
PRODUCTS_PATH = UPLOADS / "olist_products_dataset.csv"

USER_GOAL = (
    "I want to understand if shipping costs (freight_value) are impacting our "
    "sales volume and if certain product categories are more affected by delivery "
    "delays than others."
)

# ── 1. Load ────────────────────────────────────────────────────────────────────
print("Loading datasets...")
orders   = pd.read_csv(ORDERS_PATH)
items    = pd.read_csv(ITEMS_PATH)
products = pd.read_csv(PRODUCTS_PATH)
print(f"  orders:   {orders.shape}")
print(f"  items:    {items.shape}")
print(f"  products: {products.shape}")

# ── 2. Merge ───────────────────────────────────────────────────────────────────
print("\nMerging...")
merged = orders.merge(items, on="order_id", how="inner")
final  = merged.merge(products, on="product_id", how="left")
print(f"  orders ⋈ items:    {merged.shape}")
print(f"  + products (left): {final.shape}")

# ── 3. Save to temp file (data_profiler takes a file path) ────────────────────
tmp = tempfile.NamedTemporaryFile(suffix=".csv", delete=False)
tmp_path = tmp.name
tmp.close()
final.to_csv(tmp_path, index=False)

# ── 4. Profile ─────────────────────────────────────────────────────────────────
print("\nGenerating Data Profile...")
profile = generate_data_profile(tmp_path)
assert "error" not in profile, f"Profiler error: {profile['error']}"

print(f"  columns ({len(profile['columns'])}): {profile['columns']}")
print(f"  row_count: {profile['row_count']:,}")
print("  null_pct (non-zero only):")
for col, pct in profile["null_pct"].items():
    if pct > 0:
        print(f"    {col}: {pct}%")

# ── 5. Invoke Chief Planner ────────────────────────────────────────────────────
state = {
    "session_id":          "olist-test-001",
    "upload_path":         tmp_path,
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

print("\nCalling Chief Planner (live Gemini API — gemini-2.5-flash)...")
result = chief_planner_node(state)
plan   = result["plan"]

# ── 6. Print plan ──────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("CHIEF PLANNER — EXECUTION PLAN")
print("=" * 60)

print("\nCLEANING STEPS:")
for i, step in enumerate(plan["cleaning_steps"], 1):
    print(f"  {i}. {step}")

print("\nANALYSIS STEPS:")
for i, step in enumerate(plan["analysis_steps"], 1):
    print(f"  {i}. {step}")

print("\n" + "=" * 60)
print("RAW JSON:")
print(json.dumps(plan, indent=2))

# ── 7. Cleanup ─────────────────────────────────────────────────────────────────
os.unlink(tmp_path)
print("\nDone.")
