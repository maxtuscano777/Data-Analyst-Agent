"""Pydantic output schemas for ADAW agents.

All inter-agent data transfer is validated through these models to enforce
strict contracts between LangGraph nodes.
"""

from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, Field


class CleaningResult(BaseModel):
    """Output schema for Agent 1 — The Data Engineer."""

    cleaned_csv_path: str = Field(..., description="Absolute path to the cleaned CSV file in /uploads.")
    rows_before: int = Field(..., description="Row count before cleaning.")
    rows_after: int = Field(..., description="Row count after cleaning.")
    columns_dropped: list[str] = Field(default_factory=list, description="Column names that were dropped.")
    dtype_corrections: dict[str, str] = Field(
        default_factory=dict,
        description="Map of column name → new dtype (e.g. {'date': 'datetime64[ns]'}).",
    )
    execution_log: str = Field("", description="Raw Python REPL output captured during cleaning.")


class AnalysisResult(BaseModel):
    """Output schema for Agent 2 — The Statistical Analyst."""

    summary_statistics: dict[str, Any] = Field(
        default_factory=dict,
        description="Descriptive statistics keyed by column name.",
    )
    insights: list[str] = Field(default_factory=list, description="Bullet-point EDA findings.")
    model_evaluation: Optional[dict[str, Any]] = Field(
        None,
        description="Optional: model metrics (e.g. R², MAE) if forecasting was performed.",
    )
    draft_chart_paths: list[str] = Field(
        default_factory=list,
        description="Paths to draft chart PNGs generated for the HITL review.",
    )
    execution_log: str = Field("", description="Raw Python REPL output captured during analysis.")


class PresentationResult(BaseModel):
    """Output schema for Agent 3 — The Executive Presenter."""

    final_chart_paths: list[str] = Field(
        default_factory=list,
        description="Paths to polished, board-ready chart PNGs.",
    )
    executive_summary_md: str = Field("", description="Full executive narrative in Markdown.")
    execution_log: str = Field("", description="Raw Python REPL output captured during presentation.")


class AgentState(BaseModel):
    """Shared LangGraph state passed between all nodes."""

    session_id: str = Field(..., description="Unique session identifier (UUID).")
    upload_path: str = Field(..., description="Path to the original uploaded file.")
    llm_model: str = Field("gpt-4o", description="Active LLM model identifier.")
    user_query: Optional[str] = Field(None, description="Optional natural-language query from the user.")
    hitl_approved: bool = Field(False, description="Whether the HITL checkpoint has been approved.")
    hitl_feedback: Optional[str] = Field(None, description="Revision feedback from the user (if any).")
    cleaning_result: Optional[CleaningResult] = None
    analysis_result: Optional[AnalysisResult] = None
    presentation_result: Optional[PresentationResult] = None
