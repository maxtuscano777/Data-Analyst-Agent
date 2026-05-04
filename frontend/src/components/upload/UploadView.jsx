import { useState } from 'react';
import { BarChart3, Loader2, Clock } from 'lucide-react';
import { usePipelineContext } from '../../context/PipelineContext';
import { useHistory } from '../../hooks/useHistory';
import { LLM_MODELS } from '../../lib/constants';
import DropZone from './DropZone';
import SetupForm from './SetupForm';

export default function UploadView() {
  const { dispatch } = usePipelineContext();
  const { loadHistory } = useHistory();

  const [files, setFiles] = useState([]);
  const [userQuery, setUserQuery] = useState('');
  const [domainContext, setDomainContext] = useState('');
  const [llmModel, setLlmModel] = useState(LLM_MODELS[0].value);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const [error, setError] = useState(null);

  const handleShowHistory = async () => {
    setIsLoadingHistory(true);
    try {
      await loadHistory();
    } catch (err) {
      setError(err.message);
    } finally {
      setIsLoadingHistory(false);
    }
  };

  const canSubmit = files.length > 0 && userQuery.trim().length > 0 && !isSubmitting;

  const handleSubmit = async () => {
    if (!canSubmit) return;
    setIsSubmitting(true);
    setError(null);

    try {
      const fd = new FormData();
      files.forEach((f) => fd.append('files', f));
      fd.append('user_query', userQuery.trim());
      fd.append('domain_context', domainContext.trim());
      fd.append('llm_model', llmModel);

      const res = await fetch('/upload', { method: 'POST', body: fd });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `Upload failed (HTTP ${res.status})`);
      }
      const { session_id } = await res.json();
      dispatch({ type: 'SESSION_CREATED', payload: { sessionId: session_id } });
    } catch (err) {
      setError(err.message);
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen flex flex-col">
      {/* Header */}
      <header className="border-b border-gray-800 px-6 py-4">
        <div className="max-w-4xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <BarChart3 className="text-indigo-400" size={22} />
            <span className="font-semibold tracking-tight">
              ADAW — Autonomous Data Analyst Workspace
            </span>
          </div>
          <button
            onClick={handleShowHistory}
            disabled={isLoadingHistory}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-gray-800 hover:bg-gray-700
              disabled:opacity-50 text-xs text-gray-400 transition-colors"
          >
            {isLoadingHistory
              ? <Loader2 size={12} className="animate-spin" />
              : <Clock size={12} />}
            Past Runs
          </button>
        </div>
      </header>

      {/* Content */}
      <main className="flex-1 flex items-center justify-center px-4 py-12">
        <div className="w-full max-w-2xl space-y-6">
          {/* Hero */}
          <div className="text-center space-y-2">
            <h1 className="text-3xl font-bold text-white tracking-tight">
              Analyse your data
            </h1>
            <p className="text-gray-400 text-sm">
              Upload one or more CSV files, describe your business goal, and let
              the AI pipeline do the rest.
            </p>
          </div>

          {/* Card */}
          <div className="bg-gray-900 border border-gray-800 rounded-2xl p-6 space-y-6">
            <DropZone files={files} onFilesChange={setFiles} />

            <div className="border-t border-gray-800" />

            <SetupForm
              userQuery={userQuery}
              domainContext={domainContext}
              llmModel={llmModel}
              onUserQueryChange={setUserQuery}
              onDomainContextChange={setDomainContext}
              onLlmModelChange={setLlmModel}
            />

            {error && (
              <p className="text-sm text-red-400 bg-red-950/30 border border-red-900/50 rounded-lg px-4 py-2.5">
                {error}
              </p>
            )}

            <button
              onClick={handleSubmit}
              disabled={!canSubmit}
              className="w-full py-3 px-6 rounded-xl font-semibold text-sm transition-colors
                bg-indigo-600 hover:bg-indigo-500 active:bg-indigo-700
                disabled:bg-gray-800 disabled:text-gray-600 disabled:cursor-not-allowed
                flex items-center justify-center gap-2"
            >
              {isSubmitting ? (
                <>
                  <Loader2 size={15} className="animate-spin" />
                  Starting pipeline…
                </>
              ) : (
                'Run Analysis'
              )}
            </button>
          </div>
        </div>
      </main>
    </div>
  );
}
