import { useEffect, useRef } from 'react';
import { usePipelineContext } from '../context/PipelineContext';
import { WS_EVENT_TO_ACTION } from '../lib/constants';

/**
 * Opens and manages a WebSocket connection for a given sessionId.
 * Maps incoming server events to reducer dispatch calls.
 * Returns approve() and revise(feedback) for HITL interactions.
 *
 * The WebSocket is created inside a setTimeout(0) so that React StrictMode's
 * synchronous mount→cleanup→remount cycle cancels the first (transient) creation
 * via clearTimeout before the macrotask fires. Only the second, stable mount
 * actually opens a connection to the server.
 */
export function usePipeline(sessionId) {
  const { dispatch } = usePipelineContext();
  const wsRef = useRef(null);

  useEffect(() => {
    if (!sessionId) return;

    let ws = null;

    const timerId = setTimeout(() => {
      ws = new WebSocket(`/ws/pipeline/${sessionId}`);

      ws.onopen = () => {
        // Connection established — state is already 'running'
      };

      ws.onmessage = ({ data }) => {
        let msg;
        try {
          msg = JSON.parse(data);
        } catch {
          return;
        }
        const actionType = WS_EVENT_TO_ACTION[msg.type];
        if (actionType) {
          dispatch({ type: actionType, payload: msg });
        }
      };

      ws.onerror = () => {
        dispatch({ type: 'WS_ERROR', payload: { message: 'WebSocket connection error.' } });
      };

      ws.onclose = ({ code, reason }) => {
        // Abnormal closure (not triggered by a clean pipeline_complete or user reset)
        if (code !== 1000 && code !== 1001) {
          dispatch({
            type: 'WS_ERROR',
            payload: { message: `WebSocket closed unexpectedly (code ${code}${reason ? ': ' + reason : ''}).` },
          });
        }
      };

      wsRef.current = ws;
    }, 0);

    return () => {
      clearTimeout(timerId); // no-op if macrotask already fired; prevents creation during StrictMode cleanup
      if (ws) {
        ws.onclose = null;   // suppress spurious WS_ERROR on intentional unmount close
        ws.close(1000, 'component unmounted');
      }
    };
  }, [sessionId, dispatch]);

  const approve = () => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ action: 'approve' }));
      dispatch({ type: 'HITL_RESUME' });
    }
  };

  const revise = (feedback) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ action: 'revise', feedback }));
      dispatch({ type: 'HITL_RESUME' });
    }
  };

  return { approve, revise };
}
