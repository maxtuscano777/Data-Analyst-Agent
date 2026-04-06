# Project Context: Autonomous B2B Data Analyst Workspace (ADAW)

## 1. Project Overview
The ADAW is an agent-based Generative AI application that acts as an "Analyst in a Box." It autonomously cleans structured data (CSV/Excel), performs exploratory data analysis (EDA), and generates an unstructured, executive-level narrative report alongside professional visualizations. It solves the critical lack of full-time data science resources for SMEs.

## 2. Core Architecture
This system utilizes a decoupled React/FastAPI architecture with a mandatory Human-in-the-Loop (HITL) checkpoint. 

* **Frontend:** React (Vite) & Tailwind CSS
* **Backend:** FastAPI (REST & WebSockets)
* **Agentic Framework:** LangChain & LangGraph (Stateful graph architecture)
* **LLMs (Model Agnostic):** OpenAI (GPT-4o) and Hugging Face (LLaMA 3)
* **Data Science Stack:** Python, Pandas, NumPy, Scikit-learn, Matplotlib, Seaborn
* **Database & Storage:** SQLite (chat/session memory) and Local File System (`/uploads` dir)
* **Guardrails:** Pydantic
* **Deployment:** Single Docker Container (serving React via FastAPI) on AWS Fargate, monitored by Datadog.

## 3. End-to-End Pipeline
1.  **Ingestion & Storage:** User uploads a structured CSV/Excel file via React. FastAPI saves it to `/uploads` and logs the session in SQLite.
2.  **Cleaning (Agent 1):** The dataset is cleaned. FastAPI streams the raw Python execution logs back to the React UI via WebSocket.
3.  **Analysis (Agent 2):** Statistical modeling/EDA is performed. Execution logs are streamed to React.
4.  **HITL Checkpoint (WebSocket):** LangGraph pauses execution (`interrupt_before`). FastAPI streams draft charts to React. The user approves or requests revisions.
5.  **Presentation (Agent 3):** Upon approval, final polished charts and an unstructured executive narrative are generated.
6.  **Delivery:** The final report is sent to React for display and export.

## 4. Agent Roles & Specifications

### Agent 1: The Data Engineer
* **Tools:** Python REPL, Pandas.
* **Role:** Automatically writes and executes Python code to handle missing values, correct data types, drop empty columns, and standardize formatting.

### Agent 2: The Statistical Analyst
* **Tools:** Python REPL, Scikit-learn, NumPy.
* **Role:** Performs EDA and selects optimal models for trend forecasting. 
* **Strict Constraint:** Must maintain flawless statistical rigor. For example, it must actively avoid false heuristics and recognize that a decision tree with an unlimited depth will not always have zero bias. The underlying models must be evaluated logically and mathematically.

### Agent 3: The Executive Presenter
* **Tools:** Python REPL, Matplotlib, Seaborn.
* **Role:** Takes the approved insights from the HITL checkpoint, generates board-ready visualizations, and writes a comprehensive markdown executive summary.

## 5. Target Directory Structure
The workspace must adhere to the following strict directory structure:

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
│   │   └── sockets.py         # WebSocket handlers for HITL and log streaming
│   ├── agents/
│   │   ├── graph.py           # LangGraph state definition and node routing
│   │   ├── data_engineer.py   
│   │   ├── statistical_analyst.py 
│   │   ├── executive_presenter.py 
│   │   └── tools.py           # Python REPL and custom Langchain tools
│   ├── database/              # SQLite .db files for session persistence
│   ├── uploads/               # Temporary storage for user-uploaded CSV/Excel files
│   ├── schemas/
│   │   └── output_schemas.py  # Pydantic models
│   └── static/                # Compiled React build (copied here during Docker build)
│
├── .env                       # API Keys (OpenAI, HuggingFace, Datadog)
├── Dockerfile                 # Multi-stage build (Builds React -> Copies to FastAPI -> Runs Uvicorn)
└── requirements.txt           # Python dependencies