import { createContext, useContext, useReducer } from 'react';
import { PIPELINE_NODES, NODE_DISPLAY } from '../lib/constants';

// ── Initial state ──────────────────────────────────────────────────────────────

const initialNodeList = PIPELINE_NODES.map((name) => ({
  name,
  displayName: NODE_DISPLAY[name],
  status: 'pending', // 'pending' | 'running' | 'complete'
  summary: null,
}));

const initialState = {
  phase:          'idle',   // 'idle' | 'running' | 'hitl_paused' | 'complete' | 'error' | 'history'
  sessionId:      null,
  nodes:          initialNodeList,
  logs:           [],
  currentNode:    null,
  hitl:           null,     // { charts, insights, modelEvaluations }
  result:         null,     // { finalChartPaths, executiveSummaryMd }
  error:          null,
  historyList:    [],       // list of session metadata objects from GET /sessions
  historySession: null,     // session_id string when viewing a past run; null for live
};

// ── Reducer ────────────────────────────────────────────────────────────────────

function pipelineReducer(state, { type, payload }) {
  switch (type) {
    case 'SESSION_CREATED':
      return {
        ...state,
        phase:          'running',
        sessionId:      payload.sessionId,
        nodes:          initialNodeList,
        logs:           [],
        currentNode:    null,
        hitl:           null,
        result:         null,
        error:          null,
        historySession: null,
      };

    case 'NODE_START':
      return {
        ...state,
        currentNode: payload.node,
        nodes: state.nodes.map((n) =>
          n.name === payload.node ? { ...n, status: 'running' } : n
        ),
      };

    case 'LOG':
      return {
        ...state,
        logs: [...state.logs, { node: payload.node, content: payload.content }],
      };

    case 'NODE_COMPLETE':
      return {
        ...state,
        nodes: state.nodes.map((n) =>
          n.name === payload.node
            ? { ...n, status: 'complete', summary: payload.summary }
            : n
        ),
      };

    case 'HITL_PAUSE':
      return {
        ...state,
        phase: 'hitl_paused',
        hitl: {
          charts:           payload.charts,
          insights:         payload.insights,
          modelEvaluations: payload.model_evaluations,
        },
      };

    case 'HITL_RESUME':
      return {
        ...state,
        phase: 'running',
        hitl:  null,
      };

    case 'PIPELINE_COMPLETE':
      return {
        ...state,
        phase: 'complete',
        result: {
          finalChartPaths:    payload.final_chart_paths,
          executiveSummaryMd: payload.executive_summary_md,
        },
      };

    case 'WS_ERROR':
      if (state.phase === 'complete') return state;
      return {
        ...state,
        phase: 'error',
        error: payload.message || 'An unknown pipeline error occurred.',
      };

    // ── History actions ────────────────────────────────────────────────────────

    case 'HISTORY_LOADED':
      return {
        ...state,
        phase:       'history',
        historyList: payload.sessions,
      };

    case 'HISTORY_SESSION_LOADED': {
      // Merge persisted node data back into initialNodeList (preserves order + displayName)
      const nodeMap = {};
      for (const n of (payload.nodes || [])) {
        nodeMap[n.node_name] = n;
      }
      const nodes = initialNodeList.map((n) => {
        const hist = nodeMap[n.name];
        return hist ? { ...n, status: hist.status, summary: hist.summary } : n;
      });
      return {
        ...state,
        phase:          'complete',
        sessionId:      payload.session_id,
        historySession: payload.session_id,
        currentNode:    null,
        hitl:           null,
        error:          null,
        logs:           payload.logs || [],
        nodes,
        result: {
          finalChartPaths:    payload.final_chart_paths    || [],
          executiveSummaryMd: payload.executive_summary_md || '',
        },
      };
    }

    case 'RESET':
      return { ...initialState, nodes: initialNodeList };

    default:
      return state;
  }
}

// ── Context ────────────────────────────────────────────────────────────────────

const PipelineContext = createContext(null);

export function PipelineProvider({ children }) {
  const [state, dispatch] = useReducer(pipelineReducer, initialState);
  return (
    <PipelineContext.Provider value={{ state, dispatch }}>
      {children}
    </PipelineContext.Provider>
  );
}

export function usePipelineContext() {
  const ctx = useContext(PipelineContext);
  if (!ctx) throw new Error('usePipelineContext must be used inside PipelineProvider');
  return ctx;
}
