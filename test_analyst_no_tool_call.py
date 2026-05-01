"""Negative-path smoke test: Statistical Analyst with a stubbed LLM.

Verifies that when the underlying LLM never returns a tool call (simulating a
misconfigured model, wrong API credentials, or a model that ignores tool-use
instructions), the statistical_analyst_node:

  1. Does NOT crash.
  2. Returns a non-empty execution_log containing [WARNING] reprompt entries
     and a final [DIAGNOSTIC] entry explaining the failure.
  3. Returns an AnalysisResult whose insights surface the diagnostic string.
  4. Writes a non-empty analyst log file so failures are debuggable on disk.

No live LLM or REPL calls are made — ChatVertexAI is patched at module level.

Run from project root:
    PYTHONPATH=. backend/.venv/bin/python3 test_analyst_no_tool_call.py
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from langchain_core.messages import AIMessage

# Import the node AFTER load_dotenv so env vars are available.
from backend.agents.statistical_analyst import (
    _MAX_REPROMPTS,
    statistical_analyst_node,
)

# ── Constants ──────────────────────────────────────────────────────────────────
SESSION_ID  = "smoke-test-no-tool-call"
BACKEND_DIR = Path(__file__).parent / "backend"
LOGS_DIR    = BACKEND_DIR / "logs"

# Minimal state — cleaning_result is None so the node falls back to the default
# cleaned_data.csv path.  analysis_steps must be non-empty to enter the ReAct loop.
_STATE = {
    "session_id":          SESSION_ID,
    "upload_paths":        [],
    "user_query":          "Smoke test — no tool calls.",
    "domain_context":      None,
    "data_profile":        {},
    "plan":                {"cleaning_steps": [], "analysis_steps": ["Compute summary statistics."]},
    "llm_model":           "gemini-2.5-flash",
    "hitl_approved":       False,
    "hitl_feedback":       None,
    "messages":            [],
    "cleaning_result":     None,
    "analysis_result":     None,
    "presentation_result": None,
}

# ── Stub: LLM that always returns plain text, never a tool call ────────────────
_no_tool_response = AIMessage(content="I will now analyze your data...", tool_calls=[])

_mock_llm = MagicMock()
_mock_llm.bind_tools.return_value = _mock_llm   # bind_tools returns the same mock
_mock_llm.invoke.return_value = _no_tool_response

# ── Run ────────────────────────────────────────────────────────────────────────
print("=" * 60)
print("SMOKE TEST — No-Tool-Call Fallback Path")
print("=" * 60)
print(f"Patching ChatVertexAI with a stub that always returns plain text...")
print(f"_MAX_REPROMPTS = {_MAX_REPROMPTS}  (node will try this many reprompts)\n")

with patch("backend.agents.statistical_analyst.ChatVertexAI", return_value=_mock_llm):
    result = statistical_analyst_node(_STATE)

analysis_result = result["analysis_result"]

# ── Assertions ─────────────────────────────────────────────────────────────────

# 1. Node must return an AnalysisResult (no crash)
assert analysis_result is not None, \
    "FAIL: analysis_result is None — node raised or returned wrong type"

# 2. execution_log must contain [WARNING] reprompt entries
warning_entries = [e for e in analysis_result.execution_log if "[WARNING]" in e]
assert len(warning_entries) == _MAX_REPROMPTS, (
    f"FAIL: expected {_MAX_REPROMPTS} [WARNING] entries, "
    f"got {len(warning_entries)}.\n"
    f"execution_log: {analysis_result.execution_log}"
)

# 3. execution_log must contain a [DIAGNOSTIC] entry
diagnostic_entries = [e for e in analysis_result.execution_log if "[DIAGNOSTIC]" in e]
assert len(diagnostic_entries) == 1, (
    f"FAIL: expected 1 [DIAGNOSTIC] entry, got {len(diagnostic_entries)}.\n"
    f"execution_log: {analysis_result.execution_log}"
)

# 4. insights must surface the diagnostic, not an empty/generic string
assert len(analysis_result.insights) > 0, \
    "FAIL: insights list is empty"
assert "[Diagnostic]" in analysis_result.insights[0] or "REPL" in analysis_result.insights[0], (
    f"FAIL: insights[0] does not mention the REPL failure.\n"
    f"Got: {analysis_result.insights[0]!r}"
)

# 5. Analyst log on disk must exist and be non-empty
analyst_log = LOGS_DIR / f"{SESSION_ID}_analyst.log"
assert analyst_log.exists(), \
    f"FAIL: analyst log not written at {analyst_log}"
assert analyst_log.stat().st_size > 0, \
    f"FAIL: analyst log is empty (0 bytes) at {analyst_log}"

# 6. The stub LLM must have been called exactly 1 (initial) + _MAX_REPROMPTS times
expected_invoke_count = 1 + _MAX_REPROMPTS
actual_invoke_count   = _mock_llm.invoke.call_count
assert actual_invoke_count == expected_invoke_count, (
    f"FAIL: expected stub LLM to be called {expected_invoke_count} times "
    f"(1 initial + {_MAX_REPROMPTS} reprompts), got {actual_invoke_count}."
)

# ── Print diagnostics ──────────────────────────────────────────────────────────
print("execution_log entries:")
for entry in analysis_result.execution_log:
    print(f"  {entry}")

print(f"\ninsights[0]: {analysis_result.insights[0]!r}")
print(f"analyst log : {analyst_log} ({analyst_log.stat().st_size} bytes)")
print(f"stub LLM invoke() call count: {actual_invoke_count} "
      f"(expected {expected_invoke_count})")

print("\n" + "=" * 60)
print("SMOKE TEST PASSED — no-tool-call fallback path is working correctly")
print("=" * 60)
