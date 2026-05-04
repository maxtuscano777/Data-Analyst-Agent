import { usePipelineContext } from '../context/PipelineContext';

/**
 * Provides loadHistory() and loadSession(id) — each fetches from the backend
 * and dispatches the corresponding reducer action. Callers own their own
 * loading/error state since the operations are used in different UI contexts.
 */
export function useHistory() {
  const { dispatch } = usePipelineContext();

  const loadHistory = async () => {
    const res = await fetch('/sessions');
    if (!res.ok) throw new Error(`Failed to load history (HTTP ${res.status})`);
    const sessions = await res.json();
    dispatch({ type: 'HISTORY_LOADED', payload: { sessions } });
  };

  const loadSession = async (sessionId) => {
    const res = await fetch(`/sessions/${sessionId}`);
    if (!res.ok) throw new Error(`Session not found (HTTP ${res.status})`);
    const session = await res.json();
    dispatch({ type: 'HISTORY_SESSION_LOADED', payload: session });
  };

  return { loadHistory, loadSession };
}
