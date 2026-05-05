# Autonomous B2B Data Analyst Workspace — Architecture

## Executive Summary (Presentation Slide)

```mermaid
graph LR
    A["👤 User\nBusiness Analyst"]
    B["⚛ React Frontend\nUI + Live Terminal"]
    C["⚡ FastAPI Backend\nAPI + WebSocket Hub"]
    D["🧠 AI Orchestration\nLangGraph + Gemini LLM"]
    E["🔧 Execution & Storage\nPython REPL + SQLite"]

    A -->|"① Upload CSV\n& Business Goal"| B
    B -->|"② Forward\nRequest"| C
    C -->|"③ Profile + Goal\n→ Think"| D
    D -->|"④ Execute\nPlan"| E
    E -->|"⑤ Results\n& Charts"| C
    C -->|"⑥ Live Stream\nWebSocket"| B
    B -->|"⑦ HITL\nApproval"| C

    style A fill:#4A90D9,stroke:#2E6DA4,color:#fff
    style B fill:#20232A,stroke:#61DAFB,color:#61DAFB
    style C fill:#009688,stroke:#00695C,color:#fff
    style D fill:#7C3AED,stroke:#5B21B6,color:#fff
    style E fill:#F97316,stroke:#C2410C,color:#fff
```

### Data Flow Legend

| Step | Flow | Description |
|------|------|-------------|
| ① | User → Frontend | Upload CSV file + state business goal in natural language |
| ② | Frontend → Backend | HTTP request forwards file and goal to FastAPI |
| ③ | Backend → AI Orchestration | Data profile (schema + stats, not raw CSV) + user goal sent to LangGraph |
| ④ | AI Orchestration → Execution | Gemini generates a cleaning + analysis plan; agents execute it via Python REPL |
| ⑤ | Execution → Backend | Results, statistics, and charts returned to FastAPI |
| ⑥ | Backend → Frontend | Live execution logs and charts streamed back over WebSocket |
| ⑦ | Frontend → Backend | User reviews draft results and submits HITL approval (or revision request) |
