# Self-Improvement Loop & Institutional Memory

This file serves as the system's persistent memory for mistakes and corrections. Review this file before writing code to prevent recurring errors.

## Logged Lessons

---

### 2026-05-02 — ChainedAssignmentError Misdiagnosis
* **Mistake Pattern:** Diagnosed the ChainedAssignmentError as originating in the
  Data Engineer based on the error type alone, without reading the actual execution log.
* **Root Cause:** The Engineer's code was correct (used `pd.to_datetime(..., errors='coerce')`).
  The actual offender was the Statistical Analyst's median imputation loop
  (`df_model[col].fillna(df_model[col].median(), inplace=True)` — banned in Pandas 2.x CoW).
* **Prevention Rule:** ALWAYS read the full execution log for EVERY agent before
  attributing a bug to any one agent. Cross-reference log file timestamps to find the
  stage where the error first appeared. Never diagnose from error type alone.

---

### 2026-05-02 — `_MAX_REPROMPTS` Safety Net for Chatty LLMs Under Quota Pressure
* **Mistake Pattern:** Initial ReAct loops used `if not response.tool_calls: break`,
  which exits immediately on the first plain-text response. Under Vertex AI quota
  pressure, Gemini increasingly returns a polite acknowledgment turn before its first
  tool call, causing empty execution logs and AssertionErrors downstream.
* **Root Cause:** The loop had no resilience for the "polite preamble" pattern that
  large LLMs exhibit under rate-limit or quota-pressure conditions.
* **Prevention Rule:** Every REPL-based ReAct loop MUST implement the reprompt
  mechanism: track `tool_call_count` and `reprompt_count`, set `_MAX_REPROMPTS = 5`,
  and inject `_NO_TOOL_CALL_REPROMPT` before retrying. Never use bare `break` on the
  first non-tool response before the first tool call has been made.

---

### 2026-05-02 — Section-Aware Brace-Depth JSON Extraction (not regex)
* **Mistake Pattern:** Used `re.search(r"---ANALYSIS_SUMMARY---\s*(\{.*?\})\s*---END_SUMMARY---", log)`
  to extract the summary JSON. Failed in two ways: (a) the LLM often omitted
  `---END_SUMMARY---`, and (b) `.*?` (non-greedy) stopped at the first `}` inside
  a nested JSON object.
* **Root Cause:** The summary marker appears in two places in the log: inside a
  `[TOOL:]` code block (as a Python string literal in a `print()` call) AND inside an
  `[OUTPUT]` block (the actual captured REPL stdout). Regex cannot distinguish these
  two contexts, and `.*?` cannot handle nested braces.
* **Prevention Rule:** Use brace-depth character walking to find the JSON boundary.
  Before parsing, verify the marker's context: `log[:marker_pos].rfind("[OUTPUT]")`
  must be strictly greater than `log[:marker_pos].rfind("[TOOL:")`. Only parse markers
  found in `[OUTPUT]` sections. See `_extract_summary_json()` in
  `statistical_analyst.py` for the canonical implementation.

---

### 2026-05-02 — Vertex AI Rejects Messages With Empty Content
* **Mistake Pattern:** When Gemini returns a response with no text (empty `content`
  field), naively appending it to the conversation and re-invoking the LLM caused
  Vertex AI to reject the request with an error about empty `parts`.
* **Root Cause:** Vertex AI's API requires every message in the conversation to have
  non-empty `parts`. LangChain's `AIMessage` does not validate or sanitize this before
  sending to the API.
* **Prevention Rule:** All ReAct loops MUST pass their conversation through
  `_coerce_nonempty_content()` before each LLM invocation. This function replaces
  empty string content with the placeholder `"[no content]"` using `model_copy()`
  (never mutates original message objects). Copy the function verbatim from
  `data_engineer.py` or `statistical_analyst.py` — do not inline it or simplify it.

---

### 2026-05-02 — Tunnel Vision: Background Documentation Tasks Get Silently Dropped
* **Mistake Pattern:** While debugging complex code bugs (ChainedAssignmentError,
  regex failures, reprompt ceiling exhaustion), background documentation obligations —
  populating `lessons.md`, checking off `todo.md`, syncing `architecture.md` — were
  silently skipped for the entire Phase. The audit revealed `lessons.md` was still
  showing "No lessons logged yet" after a full Phase of active development.
* **Root Cause:** Deep focus on a technical bug creates tunnel vision. Non-code tasks
  produce no immediate error signal, so they stay invisible until an explicit audit pass.
* **Prevention Rule:** At the end of every multi-bug session, run a mandatory
  documentation pass BEFORE marking any phase complete:
  (a) update `lessons.md` with all mistakes made,
  (b) check off completed items in `tasks/todo.md`,
  (c) verify `architecture.md` state table matches actual `AgentState` fields.
  Treat documentation drift as a bug, not cosmetic cleanup.

---

### 2026-05-04 — WebSocket 1006 Crash After `pipeline_complete`

* **Mistake Pattern:** After sending the `pipeline_complete` message, the async
  handler simply returned. The ASGI server dropped the TCP socket without sending a
  proper WebSocket close frame. The browser fired `onclose` with code 1006 (Abnormal
  Closure), which dispatched `WS_ERROR` and overwrote the `phase: 'complete'` state,
  crashing the result view back to an error screen.
* **Root Cause:** Two compounding bugs: (1) the backend never called
  `await websocket.close(1000)`, so no WebSocket close handshake occurred; (2) the
  frontend reducer's `WS_ERROR` case unconditionally set `phase: 'error'` with no
  guard against overwriting a terminal success state.
* **Prevention Rule:** Every WebSocket handler MUST call `await websocket.close(1000)`
  after its final `send_json()` call. The `WS_ERROR` reducer case MUST guard:
  `if (state.phase === 'complete') return state;` — a connection drop after success
  is expected and must never clobber the result.

---

### 2026-05-04 — LangGraph `astream_events(v2)` Event Schema Is Asymmetric

* **Mistake Pattern:** Consolidated TOOL code extraction and OUTPUT extraction into
  a single `on_tool_end` handler (reasoning: "both pieces of data available at
  end"). `data["input"]` was always `None` in `on_tool_end`, so every TOOL message
  was silently dropped. OUTPUT blocks continued to appear, masking the problem.
* **Root Cause:** LangGraph's `astream_events(v2)` schema is strictly asymmetric:
  `on_tool_start` carries `data["input"]` (code) but NOT `data["output"]`;
  `on_tool_end` carries `data["output"]` (stdout) but NOT `data["input"]`. The two
  fields are never present in the same event.
* **Prevention Rule:** ALWAYS split tool event handling across the two events:
  extract code from `on_tool_start`, extract output from `on_tool_end`. Never
  consolidate them. Treat the event schema as write-once per field.

---

### 2026-05-04 — Silent Suppression via `data.get("input", {})` Default

* **Mistake Pattern:** Used `raw_input = data.get("input", {})` when the `"input"`
  key might be absent. Because `isinstance({}, dict)` is `True`, the branch then
  called `{}.get("query", "")` which returned `""`. The `if code:` guard silently
  dropped the message with no exception, no log line, and no visible error.
* **Root Cause:** Defaulting to `{}` when a key is absent conflates "key missing"
  with "key present but empty dict". Both produce the same code path, so absence
  becomes invisible.
* **Prevention Rule:** When absence vs. emptiness must be distinguishable, always
  use `data.get("input")` (no default). Check `if raw_input is None` explicitly.
  A missing key and an empty dict are different conditions and must be handled
  separately.

---

### 2026-05-04 — LangGraph Drops Positional String Arguments From Event Stream

* **Mistake Pattern:** Called `repl.invoke(code_snippet, config=config)` with the
  code as a raw positional string. The REPL tool executed correctly and returned
  output, but `on_tool_start` consistently emitted `data={'input': {}}` — the code
  was completely absent from the event stream. Confirmed via `print(f"[DEBUG]
  on_tool_start data={data!r}", flush=True)`.
* **Root Cause:** LangChain's `astream_events(v2)` serializer expects tool inputs
  to be a dict matching the tool's Pydantic schema. `PythonAstREPLTool` declares
  `query: str`. When a bare string is passed positionally, the serializer cannot
  map it to a named field and serializes the input as `{}`. The code executes fine
  but is erased from the event payload.
* **Prevention Rule:** Always invoke REPL tools with a keyword-argument dict:
  `repl.invoke({"query": code_snippet}, config=config)`. Never pass tool inputs as
  bare positional strings when `astream_events` observability is required.
  The debug `print(f"[DEBUG] on_tool_start data={data!r}", flush=True)` pattern
  is the fastest way to diagnose event payload issues — add it temporarily whenever
  `data["input"]` is suspected empty.

---

### 2026-05-04 — React 18/19 StrictMode Kills WebSocket on First Mount

* **Mistake Pattern:** Created the WebSocket directly inside `useEffect`. In
  development, React 18/19 StrictMode runs mount → cleanup → remount
  synchronously. The cleanup fired `ws.close(1000)` before the server had started
  the pipeline, then the remount opened a new connection to an already-running
  graph. The server streamed events into the dead first connection; the second
  connection got nothing.
* **Root Cause:** StrictMode's intentional double-invoke of effects exposes
  cleanup bugs. A WebSocket opened in the synchronous effect body is created and
  destroyed within the same scheduler flush before any remount work begins.
* **Prevention Rule:** Defer WebSocket creation with `setTimeout(0)` — this moves
  creation into a macrotask that fires after the synchronous mount→cleanup→remount
  cycle completes. In the cleanup function, call `clearTimeout(timerId)` (no-op if
  macrotask already fired) and `ws.onclose = null; ws.close(1000, ...)` to suppress
  the spurious `WS_ERROR` on intentional unmount close. See `usePipeline.js` for
  the canonical implementation.

---

### 2026-05-05 — LangGraph Eager Edge Evaluation Bypasses HITL Routing

* **Mistake Pattern:** Used a static edge `add_edge("statistical_analyst", "executive_presenter")`
  combined with `interrupt_before=["executive_presenter"]`. When the user clicked "Revise"
  and injected feedback via `graph.update_state()`, the pipeline ignored the feedback and ran
  `executive_presenter` anyway — exactly as if "Approve" had been clicked.
* **Root Cause:** LangGraph evaluates edges **eagerly** and writes the routing decision into
  the checkpoint *before* honoring `interrupt_before`. By the time the graph pauses, the next
  node (`executive_presenter`) is already locked in the checkpoint. `update_state` updates the
  state but cannot change the pre-committed routing target. Resuming simply executes the
  queued node.
* **Prevention Rule:** Never use `interrupt_before` on the final destination node when the
  routing decision depends on state injected after the pause. Instead, insert a lightweight
  **sentinel node** (`hitl_router_node` returning `{}`) *before* the destination. Fire
  `interrupt_before` on the sentinel. When the graph resumes, the sentinel runs, and a
  **conditional edge** re-evaluates the current state to decide where to go. The routing
  decision is deferred until after `update_state` — which is the correct lifecycle order.
  Also wrap the Phase 2 streaming loop in a `while True` so multiple revision cycles are
  supported without restructuring the WebSocket handler.
