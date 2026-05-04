import { useState } from 'react';
import { BarChart3, Plus, FileText, CheckCircle2, XCircle, Loader2, Clock, ChevronRight, AlertCircle } from 'lucide-react';
import { usePipelineContext } from '../../context/PipelineContext';
import { useHistory } from '../../hooks/useHistory';

// ── Helpers ────────────────────────────────────────────────────────────────────

function formatDate(isoStr) {
  if (!isoStr) return '—';
  // SQLite datetime('now') returns "YYYY-MM-DD HH:MM:SS" (UTC)
  const d = new Date(isoStr.replace(' ', 'T') + 'Z');
  return d.toLocaleString(undefined, {
    month: 'short', day: 'numeric', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });
}

const STATUS_CONFIG = {
  complete:    { label: 'Complete',   color: 'text-emerald-400 bg-emerald-950/50 border-emerald-800/50', Icon: CheckCircle2 },
  error:       { label: 'Error',      color: 'text-red-400 bg-red-950/50 border-red-800/50',             Icon: XCircle      },
  running:     { label: 'Running',    color: 'text-amber-400 bg-amber-950/50 border-amber-800/50',        Icon: Loader2      },
  hitl_paused: { label: 'Paused',     color: 'text-amber-400 bg-amber-950/50 border-amber-800/50',        Icon: Clock        },
  uploaded:    { label: 'Pending',    color: 'text-gray-400 bg-gray-800/50 border-gray-700/50',            Icon: Clock        },
};

function StatusBadge({ status }) {
  const cfg = STATUS_CONFIG[status] ?? STATUS_CONFIG.uploaded;
  const { label, color, Icon } = cfg;
  return (
    <span className={`inline-flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full border ${color}`}>
      <Icon size={10} />
      {label}
    </span>
  );
}

// ── Session card ───────────────────────────────────────────────────────────────

function SessionCard({ session }) {
  const { loadSession } = useHistory();
  const [loading, setLoading] = useState(false);
  const [err, setErr]         = useState(null);

  const handleView = async () => {
    setLoading(true);
    setErr(null);
    try {
      await loadSession(session.session_id);
    } catch (e) {
      setErr(e.message);
      setLoading(false);
    }
  };

  const fileList = (session.file_names || []).join(', ') || '—';
  const canView  = session.status === 'complete';

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 flex items-start gap-4 hover:border-gray-700 transition-colors">
      {/* Icon */}
      <div className="p-2 rounded-lg bg-indigo-950/50 border border-indigo-900/50 shrink-0 mt-0.5">
        <FileText size={16} className="text-indigo-400" />
      </div>

      {/* Body */}
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-gray-100 line-clamp-2 leading-snug">
          {session.user_query}
        </p>
        <div className="flex items-center gap-2 mt-1.5 flex-wrap">
          <span className="text-xs text-gray-500">{fileList}</span>
          <span className="text-gray-700 text-xs">·</span>
          <span className="text-xs text-gray-500">{formatDate(session.created_at)}</span>
        </div>
        {err && (
          <p className="mt-2 text-xs text-red-400 flex items-center gap-1">
            <AlertCircle size={11} /> {err}
          </p>
        )}
      </div>

      {/* Right side */}
      <div className="flex items-center gap-2.5 shrink-0">
        <StatusBadge status={session.status} />
        {canView && (
          <button
            onClick={handleView}
            disabled={loading}
            className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500
              disabled:bg-indigo-900/50 disabled:text-indigo-700
              text-xs font-medium text-white transition-colors"
          >
            {loading ? <Loader2 size={12} className="animate-spin" /> : <ChevronRight size={12} />}
            View
          </button>
        )}
      </div>
    </div>
  );
}

// ── Main view ──────────────────────────────────────────────────────────────────

export default function HistoryView() {
  const { state, dispatch } = usePipelineContext();
  const { historyList } = state;

  return (
    <div className="min-h-screen flex flex-col">
      {/* Header */}
      <header className="border-b border-gray-800 px-6 py-4 shrink-0">
        <div className="max-w-4xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <BarChart3 className="text-indigo-400" size={22} />
            <span className="font-semibold tracking-tight">ADAW — Past Runs</span>
          </div>
          <button
            onClick={() => dispatch({ type: 'RESET' })}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500
              text-xs font-medium text-white transition-colors"
          >
            <Plus size={12} />
            New Analysis
          </button>
        </div>
      </header>

      {/* Content */}
      <main className="flex-1 max-w-4xl mx-auto w-full px-6 py-8">
        {historyList.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-24 gap-3 text-center">
            <Clock size={32} className="text-gray-700" />
            <p className="text-gray-500 text-sm">No past runs yet.</p>
            <p className="text-gray-600 text-xs">
              Completed analyses will appear here.
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {historyList.map((session) => (
              <SessionCard key={session.session_id} session={session} />
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
