import { BarChart3, AlertTriangle } from 'lucide-react';
import { usePipelineContext } from '../../context/PipelineContext';
import { usePipeline } from '../../hooks/usePipeline';
import NodeStatusBar from './NodeStatusBar';
import LiveTerminal from './LiveTerminal';
import HitlModal from '../hitl/HitlModal';

export default function PipelineView() {
  const { state, dispatch } = usePipelineContext();
  const { phase, sessionId, error } = state;
  const { approve, revise } = usePipeline(sessionId);

  return (
    <div className="min-h-screen flex flex-col">
      {/* Header */}
      <header className="border-b border-gray-800 px-6 py-4 shrink-0">
        <div className="max-w-5xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <BarChart3 className="text-indigo-400" size={22} />
            <span className="font-semibold tracking-tight">ADAW — Pipeline Running</span>
          </div>
          <span className="text-xs text-gray-700 font-mono hidden sm:block">
            {sessionId}
          </span>
        </div>
      </header>

      {/* Main content */}
      <main className="flex-1 flex flex-col max-w-5xl mx-auto w-full px-6 py-6 gap-5">
        <NodeStatusBar />

        {phase === 'error' ? (
          <div className="flex-1 flex items-center justify-center py-20">
            <div className="text-center space-y-3">
              <AlertTriangle size={40} className="text-red-400 mx-auto" />
              <p className="text-red-400 font-semibold">Pipeline Error</p>
              <p className="text-gray-500 text-sm max-w-sm">{error}</p>
              <button
                onClick={() => dispatch({ type: 'RESET' })}
                className="mt-2 px-4 py-2 rounded-lg bg-gray-800 hover:bg-gray-700 text-sm text-gray-300 transition-colors"
              >
                Start Over
              </button>
            </div>
          </div>
        ) : (
          <LiveTerminal />
        )}
      </main>

      {/* HITL overlay — rendered on top when phase is 'hitl_paused' */}
      {phase === 'hitl_paused' && (
        <HitlModal approve={approve} revise={revise} />
      )}
    </div>
  );
}
