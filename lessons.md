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
