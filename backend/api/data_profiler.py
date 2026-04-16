"""Data Profile Extractor — NO LLM calls permitted in this file.

Generates a compact, LLM-safe summary of an uploaded CSV or Excel file.
The raw file is NEVER passed to any language model; only this profile is.

Public API:
    generate_data_profile(file_path: str) -> dict
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pandas as pd


def generate_data_profile(file_path: str) -> dict[str, Any]:
    """Load a CSV or Excel file and return a compact Data Profile dict.

    The profile contains enough structural information for the Chief Planner
    to reason about what cleaning and analysis steps are needed, without
    exposing the full dataset to the LLM context window.

    Args:
        file_path: Absolute path to the uploaded CSV or Excel file.

    Returns:
        On success:
        {
            "columns":     list[str]          — ordered column names
            "dtypes":      dict[str, str]     — column → pandas dtype string
            "null_counts": dict[str, int]     — column → count of NaN values
            "null_pct":    dict[str, float]   — column → % missing (0–100, 2 dp)
            "row_count":   int                — total rows in the raw file
            "sample_data": list[dict]         — first 5 rows as list of records
        }

        On failure:
        {
            "error": str   — human-readable error message
        }
    """
    path = Path(file_path)

    # ── Load ──────────────────────────────────────────────────────────────────
    try:
        if path.suffix.lower() in {".xlsx", ".xls"}:
            df = pd.read_excel(path)
        elif path.suffix.lower() == ".csv":
            df = pd.read_csv(path)
        else:
            return {"error": f"Unsupported file type '{path.suffix}'. Expected .csv, .xlsx, or .xls."}
    except FileNotFoundError:
        return {"error": f"File not found: {file_path}"}
    except pd.errors.EmptyDataError:
        return {"error": f"File is empty: {file_path}"}
    except Exception as exc:  # noqa: BLE001
        return {"error": f"Failed to read file: {exc}"}

    # ── Profile ───────────────────────────────────────────────────────────────
    try:
        row_count: int = len(df)
        columns: list[str] = df.columns.tolist()
        dtypes: dict[str, str] = {col: str(df[col].dtype) for col in columns}
        null_counts: dict[str, int] = {col: int(df[col].isna().sum()) for col in columns}
        null_pct: dict[str, float] = {
            col: round(null_counts[col] / row_count * 100, 2) if row_count > 0 else 0.0
            for col in columns
        }

        # Convert head(5) to JSON-safe records — replace NaN/Inf with None
        sample_raw: list[dict] = df.head(5).to_dict(orient="records")
        sample_data: list[dict] = [_sanitize_record(row) for row in sample_raw]

        return {
            "columns": columns,
            "dtypes": dtypes,
            "null_counts": null_counts,
            "null_pct": null_pct,
            "row_count": row_count,
            "sample_data": sample_data,
        }

    except Exception as exc:  # noqa: BLE001
        return {"error": f"Profiling failed after load: {exc}"}


def _sanitize_record(record: dict) -> dict:
    """Replace float NaN / ±Inf with None so the profile is JSON-serializable."""
    cleaned = {}
    for key, value in record.items():
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            cleaned[key] = None
        else:
            cleaned[key] = value
    return cleaned
