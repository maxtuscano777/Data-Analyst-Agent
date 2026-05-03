# Project Context: Autonomous B2B Data Analyst Workspace (ADAW)

## 1. Project Overview
The ADAW is an agent-based Generative AI application that acts as an "Analyst in a Box." It autonomously cleans structured data (CSV/Excel), performs exploratory data analysis (EDA), and generates an unstructured, executive-level narrative report alongside professional visualizations. It solves the critical lack of full-time data science resources for SMEs.

## 2. Core Architecture
This system utilizes a decoupled React/FastAPI architecture with a mandatory Human-in-the-Loop (HITL) checkpoint.

* **Frontend:** React (Vite) & Tailwind CSS
* **Backend:** FastAPI (REST & WebSockets)
* **Agentic Framework:** LangChain & LangGraph (Stateful graph architecture)
* **Agentic Pattern:** Planner-Executor (Supervisor) — Chief Planner generates a strict JSON execution plan from a compact Data Profile; downstream agents are deterministic executors of that plan.
* **LLMs (Model Agnostic):** Google Gemini (primary) and Hugging Face (LLaMA 3)
* **Data Science Stack:** Python, Pandas, NumPy, Scikit-learn, Matplotlib, Seaborn
* **Database & Storage:** SQLite (chat/session memory) and Local File System (`/uploads` dir)
* **Guardrails:** Pydantic
* **Deployment:** Single Docker Container (serving React via FastAPI) on AWS Fargate, monitored by Datadog.

## 3. End-to-End Pipeline
1.  **Ingestion & Storage:** User uploads a structured CSV/Excel file via React. FastAPI saves it to `/uploads` and logs the session in SQLite.
2.  **Data Profile Extraction (Automated, no LLM):** FastAPI runs a lightweight Python script (`data_profiler.py`) that extracts column names, dtypes, null counts, and `df.head(3)`. This compact "Data Profile" JSON is stored in the session state. The raw CSV is **NEVER** passed to any LLM.
3.  **Planning (Agent 1 — Chief Planner):** Receives the User's Business Goal (natural language) + the Data Profile JSON. Outputs a strict JSON execution plan with two keys: `cleaning_steps` (ordered list for Agent 2) and `analysis_steps` (ordered list for Agent 3). The Planner does NOT write or execute any code.
4.  **Cleaning (Agent 2 — Data Engineer):** Reads `cleaning_steps` from the plan and executes them sequentially using Pandas via Python REPL. FastAPI streams the raw execution logs back to the React UI via WebSocket.
5.  **Analysis (Agent 3 — Statistical Analyst):** Reads `analysis_steps` from the plan and executes them using Scikit-learn/NumPy via Python REPL. Execution logs are streamed to React.
6.  **HITL Checkpoint (WebSocket):** LangGraph pauses execution (`interrupt_before`). FastAPI streams draft charts to React. The user approves or requests revisions.
7.  **Presentation (Agent 4 — Executive Presenter):** Upon approval, generates polished charts and a comprehensive executive Markdown narrative. Final report sent to React for display and export.

## 4. Agent Roles & Specifications

### Agent 1: The Chief Planner
* **Input:** User's business goal (natural language) + Data Profile JSON (column names, dtypes, null counts, `df.head(3)`).
* **Output:** A strict JSON execution plan:
  ```json
  {
    "cleaning_steps": [
      "Drop columns where null percentage exceeds 50%",
      "Parse the 'date' column as datetime64",
      "Fill missing numeric values with column median"
    ],
    "analysis_steps": [
      "Compute and print a correlation matrix for all numeric columns",
      "Fit a LinearRegression model on target column 'revenue'; evaluate with cross_val_score(cv=5)"
    ]
  }
  ```
* **Constraint:** Does NOT receive the full CSV. Does NOT write or execute any code. Its sole responsibility is to reason about what should be done and produce an unambiguous, ordered plan.

### Agent 2: The Data Engineer
* **Tools:** Python REPL, Pandas.
* **Role:** Reads `cleaning_steps` from the Chief Planner's JSON plan and executes each step sequentially. No longer operates autonomously from scratch — all decisions were made by the Planner.

### Agent 3: The Statistical Analyst
* **Tools:** Python REPL, Scikit-learn, NumPy.
* **Role:** Reads `analysis_steps` from the Chief Planner's JSON plan and executes them. Maintains strict statistical rigor — cross-validation is required; false heuristics (e.g. claiming zero bias for an unconstrained decision tree) are prohibited.

### Agent 4: The Executive Presenter
* **Tools:** Python REPL, Matplotlib, Seaborn.
* **Role:** Takes the approved insights from the HITL checkpoint, generates board-ready visualizations, and writes a comprehensive Markdown executive summary.

## 5. Target Directory Structure
The workspace must adhere to the following strict directory structure:

```
data-analyst-agent/
│
├── frontend/                  # React SPA (Vite)
│   ├── src/
│   │   ├── components/        # React UI components (Upload, HITL Dashboard, Charts, Terminal Logs)
│   │   ├── hooks/             # Custom hooks for API and WebSocket communication
│   │   └── App.jsx            # Main React application
│   └── package.json
│
├── backend/                   # FastAPI + LangGraph Backend
│   ├── api/
│   │   ├── main.py            # FastAPI application and REST endpoint routing
│   │   ├── sockets.py         # WebSocket handlers for HITL and log streaming
│   │   └── data_profiler.py   # Automated CSV profiling script (no LLM)
│   ├── agents/
│   │   ├── graph.py           # LangGraph state definition and node routing
│   │   ├── chief_planner.py   # Agent 1: generates JSON execution plan from Data Profile
│   │   ├── data_engineer.py   # Agent 2: executes cleaning_steps from plan
│   │   ├── statistical_analyst.py  # Agent 3: executes analysis_steps from plan
│   │   ├── executive_presenter.py  # Agent 4: final charts + executive narrative
│   │   └── tools.py           # Python REPL and custom Langchain tools
│   ├── database/              # SQLite .db files for session persistence
│   ├── uploads/               # Temporary storage for user-uploaded CSV/Excel files
│   ├── schemas/
│   │   └── output_schemas.py  # Pydantic models + AgentState TypedDict (includes `plan` field)
│   └── static/                # Compiled React build (copied here during Docker build)
│
├── .env                       # API Keys (Google Gemini, HuggingFace, Datadog)
├── Dockerfile                 # Multi-stage build (Builds React -> Copies to FastAPI -> Runs Uvicorn)
└── requirements.txt           # Python dependencies
```

## 6. LangGraph State — `AgentState`
The shared state TypedDict passed between all nodes. Key fields:

| Field | Type | Description |
|---|---|---|
| `session_id` | `str` | Unique session UUID |
| `upload_paths` | `list[str]` | Absolute paths to uploaded CSV/Excel files. Single-file uploads: list with one element. Multi-file: one path per file, in upload order. |
| `domain_context` | `Optional[str]` | Optional industry or business context (e.g. 'E-commerce logistics') injected into the Chief Planner's prompt to guide domain-specific analysis decisions. |
| `data_profile` | `Optional[dict]` | Output of `data_profiler.py` (columns, dtypes, nulls, head) |
| `plan` | `Optional[dict]` | Chief Planner's JSON output: `{"cleaning_steps": [...], "analysis_steps": [...]}` |
| `llm_model` | `str` | Active LLM model identifier (default: `gemini-2.0-flash`) |
| `user_query` | `Optional[str]` | User's business goal / natural-language query |
| `hitl_approved` | `bool` | Whether the HITL checkpoint has been approved |
| `hitl_feedback` | `Optional[str]` | Revision feedback from the user (if any) |
| `messages` | `Annotated[list, add_messages]` | Accumulated LLM conversation history |
| `cleaning_result` | `Optional[CleaningResult]` | Output of Agent 2 |
| `analysis_result` | `Optional[AnalysisResult]` | Output of Agent 3 |
| `presentation_result` | `Optional[PresentationResult]` | Output of Agent 4 |
