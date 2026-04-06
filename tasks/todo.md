# Development Checklist: ADAW Pipeline

## Phase 1: Environment & Tooling
- [ ] Initialize frontend repository (React/Vite + Tailwind CSS).
- [ ] Initialize backend repository (FastAPI + Python environment).
- [ ] Set up local SQLite database for session memory.
- [ ] Configure local `/uploads` directory for CSV/Excel storage.

## Phase 2: Core Backend Logic (LangGraph)
- [ ] Build Agent 1 (Data Engineer): Pandas REPL tools for CSV cleaning.
- [ ] Build Agent 2 (Statistical Analyst): Scikit-learn/NumPy tools for EDA. Ensure strict statistical rigor.
- [ ] Build Agent 3 (Executive Presenter): Matplotlib/Seaborn tools + Markdown generation.
- [ ] Configure LangGraph `StateGraph` and node routing.
- [ ] Define Pydantic output schemas for all agents.

## Phase 3: The Human-in-the-Loop & API
- [ ] Implement LangGraph `MemorySaver` checkpointer.
- [ ] Set `interrupt_before=["executive_presenter"]` in the graph compiler.
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