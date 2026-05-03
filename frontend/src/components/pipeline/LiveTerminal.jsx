import { useRef } from 'react';
import { Terminal } from 'lucide-react';
import { usePipelineContext } from '../../context/PipelineContext';
import { useAutoScroll } from '../../hooks/useAutoScroll';

// Per-agent accent colours so log sections are visually distinct
const NODE_COLOR = {
  chief_planner:       'text-cyan-400',
  data_engineer:       'text-amber-400',
  statistical_analyst: 'text-emerald-400',
  executive_presenter: 'text-purple-400',
};

// Lines that act as structural headers inside a log entry
const isHeaderLine = (line) =>
  line.startsWith('[TOOL:') ||
  line.startsWith('[OUTPUT]') ||
  line.startsWith('[WARNING]') ||
  line.startsWith('[ERROR]');

export default function LiveTerminal() {
  const { state } = usePipelineContext();
  const { logs, currentNode, nodes } = state;
  const scrollRef = useRef(null);

  useAutoScroll(scrollRef, [logs.length]);

  const currentNodeDisplay = nodes.find((n) => n.name === currentNode)?.displayName;

  return (
    <div className="flex flex-col bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
      {/* macOS-style title bar */}
      <div className="flex items-center gap-2 px-4 py-2.5 border-b border-gray-800 bg-gray-900/90 shrink-0">
        <span className="w-3 h-3 rounded-full bg-red-500/50" />
        <span className="w-3 h-3 rounded-full bg-yellow-500/50" />
        <span className="w-3 h-3 rounded-full bg-green-500/50" />
        <Terminal size={12} className="text-gray-600 ml-2" />
        <span className="text-xs text-gray-600 font-mono">
          {currentNodeDisplay ? `agent › ${currentNodeDisplay}` : 'execution log'}
        </span>
      </div>

      {/* Scrollable log body */}
      <div
        ref={scrollRef}
        className="overflow-y-auto p-4 font-mono text-xs leading-relaxed bg-black min-h-96 max-h-[60vh]"
      >
        {logs.length === 0 ? (
          <span className="text-gray-700">Waiting for agent output…</span>
        ) : (
          logs.map((entry, i) => {
            const accentClass = NODE_COLOR[entry.node] ?? 'text-gray-400';
            const lines = entry.content.split('\n');

            return (
              <div key={i} className="mb-3 border-l-2 border-gray-800 pl-3">
                {lines.map((line, j) =>
                  isHeaderLine(line) ? (
                    <div key={j} className={`font-bold ${accentClass}`}>{line}</div>
                  ) : (
                    <div key={j} className="text-gray-300 whitespace-pre-wrap break-words">
                      {line}
                    </div>
                  )
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
