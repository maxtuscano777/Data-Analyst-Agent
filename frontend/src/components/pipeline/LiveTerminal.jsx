import { useRef } from 'react';
import { Terminal } from 'lucide-react';
import SyntaxHighlighter from 'react-syntax-highlighter/dist/esm/prism';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { usePipelineContext } from '../../context/PipelineContext';
import { useAutoScroll } from '../../hooks/useAutoScroll';

const NODE_COLOR = {
  chief_planner:       'text-cyan-400',
  data_engineer:       'text-amber-400',
  statistical_analyst: 'text-emerald-400',
  executive_presenter: 'text-purple-400',
};

const NODE_BORDER = {
  chief_planner:       'border-cyan-800',
  data_engineer:       'border-amber-800',
  statistical_analyst: 'border-emerald-800',
  executive_presenter: 'border-purple-800',
};

const TOOL_MARKER   = '[TOOL: python_repl_ast]';
const OUTPUT_MARKER = '[OUTPUT]';

function parseLogEntry(content) {
  const trimmed = content.trim();

  if (trimmed.startsWith(TOOL_MARKER)) {
    const code = trimmed.slice(TOOL_MARKER.length).replace(/^[\r\n]+/, '');
    return { kind: 'tool', code };
  }
  if (trimmed.startsWith(OUTPUT_MARKER)) {
    const text = trimmed.slice(OUTPUT_MARKER.length).replace(/^[\r\n]+/, '');
    return { kind: 'output', text };
  }
  if (trimmed.startsWith('[WARNING]') || trimmed.startsWith('[ERROR]')) {
    return { kind: 'warning', text: content };
  }
  return { kind: 'plain', text: content };
}

function LogEntry({ entry }) {
  const accentClass  = NODE_COLOR[entry.node]  ?? 'text-gray-400';
  const borderClass  = NODE_BORDER[entry.node] ?? 'border-gray-800';
  const parsed = parseLogEntry(entry.content);

  return (
    <div className={`mb-3 border-l-2 ${borderClass} pl-3`}>
      {parsed.kind === 'tool' && (
        <div>
          <div className={`text-[10px] font-semibold uppercase tracking-widest mb-1 ${accentClass}`}>
            python
          </div>
          <SyntaxHighlighter
            language="python"
            style={vscDarkPlus}
            customStyle={{
              margin: 0,
              padding: '10px 12px',
              borderRadius: '6px',
              fontSize: '11px',
              lineHeight: '1.6',
              background: '#1e1e2e',
            }}
            wrapLongLines
          >
            {parsed.code}
          </SyntaxHighlighter>
        </div>
      )}

      {parsed.kind === 'output' && (
        <div>
          <div className="text-[10px] font-semibold uppercase tracking-widest text-gray-600 mb-1">
            stdout
          </div>
          <pre className="text-emerald-300/80 whitespace-pre-wrap break-words text-xs leading-relaxed bg-gray-950 rounded-md px-3 py-2 border border-gray-800">
            {parsed.text}
          </pre>
        </div>
      )}

      {parsed.kind === 'warning' && (
        <div className="text-amber-400 whitespace-pre-wrap break-words">
          {parsed.text}
        </div>
      )}

      {parsed.kind === 'plain' && (
        <div className="text-gray-400 whitespace-pre-wrap break-words">
          {parsed.text}
        </div>
      )}
    </div>
  );
}

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
          logs.map((entry, i) => <LogEntry key={i} entry={entry} />)
        )}
      </div>
    </div>
  );
}
