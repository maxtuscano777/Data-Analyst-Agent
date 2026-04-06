"""Custom LangChain tools for ADAW agents.

All agents share a sandboxed Python REPL tool. Output is captured and
returned as a string so it can be streamed back to the frontend.
"""

from langchain_experimental.tools import PythonREPLTool

# Shared Python REPL — stateful within a single agent invocation.
# Each agent node should instantiate its own copy to avoid cross-contamination.
python_repl = PythonREPLTool()


def get_python_repl() -> PythonREPLTool:
    """Return a fresh PythonREPLTool instance for an agent node."""
    return PythonREPLTool()
