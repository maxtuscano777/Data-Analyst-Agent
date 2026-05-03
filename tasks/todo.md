# Development Checklist: ADAW Pipeline

## Phase 1: Environment & Tooling
- [✓] Initialize frontend repository (React/Vite + Tailwind CSS).
- [✓] Initialize backend repository (FastAPI + Python environment).
- [✓] Set up local SQLite database for session memory.
- [✓] Configure local `/uploads` directory for CSV/Excel storage.

## Phase 2: Core Backend Logic (LangGraph — Planner-Executor Pattern)

### 2a. Schemas & State
- [✓] **[@Paras + @Max]** Add `plan: Optional[dict]` and `data_profile: Optional[dict]` fields to `AgentState` TypedDict (`output_schemas.py`).

### 2b. Data Profile Extraction (No LLM)
- [✓] **[@Paras]** Build `backend/api/data_profiler.py`: automated script that extracts column names, dtypes, null counts, and `df.head(5)` from the uploaded file. Returns a compact JSON profile. Called by FastAPI before invoking the LangGraph graph.

### 2c. Agent 1 — Chief Planner (NEW)
- [✓] **[@Paras]** Build `backend/agents/chief_planner.py`: LLM node (Gemini, no REPL tool) that receives [User's Business Goal + Data Profile] and outputs a strict JSON plan with `cleaning_steps` and `analysis_steps`. No access to the full CSV.

### 2d. Agent 2 — Data Engineer
- [✓] **[@Paras]** Build `backend/agents/data_engineer.py`: Pandas REPL executor. Reads `cleaning_steps` from `state["plan"]` and executes them sequentially (no autonomous planning).

### 2e. Agent 3 — Statistical Analyst
- [✓] **[@Max]** Build `backend/agents/statistical_analyst.py`: Scikit-learn/NumPy REPL executor. Reads `analysis_steps` from `state["plan"]`. Strict statistical rigor maintained (cross-val required, no false heuristics). Parses `---ANALYSIS_SUMMARY---` block for structured insights + ModelEvaluation output.

### 2f. Agent 4 — Executive Presenter
- [✓] **[@Max]** Build `backend/agents/executive_presenter.py`: Two-phase — Phase 1 REPL polishes Matplotlib/Seaborn charts; Phase 2 LLM generates Markdown executive narrative. Triggered after HITL approval.

### 2g. LangGraph Routing
- [✓] **[@Paras + @Max]** Updated `backend/agents/graph.py`: added `chief_planner` node as first node after START; full pipeline `chief_planner → data_engineer → statistical_analyst → [HITL] → executive_presenter → END`.

## Phase 3: The Human-in-the-Loop & API
- [✓] Implement LangGraph `MemorySaver` checkpointer.
- [✓] Set `interrupt_before=["executive_presenter"]` in the graph compiler.
- [ ] Build FastAPI WebSocket endpoints for streaming agent execution logs.
- [ ] Build FastAPI WebSocket endpoints for the HITL pause/approval cycle.

## Phase 4: Frontend Development
- [ ] Build File Uploader component (CSV/Excel).
- [ ] Build LLM Toggle Dropdown (Model Agnosticism).
- [ ] Build Live Terminal UI component to display WebSocket agent logs.
- [ ] Build HITL Dashboard (displaying draft charts and Approve/Revise buttons).
- [ ] Build Final Report view with "Export to PDF/Markdown" functionality.

## Phase 5: Deployment
- [ ] Write Dockerfile to serve compiled React dist via FastAPI.
- [ ] Test single-container deployment locally.
- [ ] Deploy to AWS Fargate.
- [ ] Integrate Datadog for monitoring and API token tracking.
