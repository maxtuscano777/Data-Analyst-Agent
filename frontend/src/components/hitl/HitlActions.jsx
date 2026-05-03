import { useState } from 'react';
import { ThumbsUp, MessageSquare, Send, X } from 'lucide-react';

export default function HitlActions({ approve, revise }) {
  const [mode, setMode] = useState('idle'); // 'idle' | 'revise'
  const [feedback, setFeedback] = useState('');

  const handleRevise = () => {
    if (!feedback.trim()) return;
    revise(feedback.trim());
  };

  const handleCancel = () => {
    setMode('idle');
    setFeedback('');
  };

  if (mode === 'revise') {
    return (
      <div className="space-y-3">
        <p className="text-sm text-gray-400">
          Describe what should be changed or added to the analysis:
        </p>
        <textarea
          value={feedback}
          onChange={(e) => setFeedback(e.target.value)}
          placeholder="e.g. Please add a revenue trend by month chart. Also investigate whether seller state correlates with delivery delays."
          rows={3}
          autoFocus
          className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2.5 text-sm text-gray-100
            placeholder:text-gray-600 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500
            resize-none transition-colors"
        />
        <div className="flex items-center gap-3">
          <button
            onClick={handleRevise}
            disabled={!feedback.trim()}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500
              disabled:bg-gray-800 disabled:text-gray-600 disabled:cursor-not-allowed
              text-sm font-medium transition-colors"
          >
            <Send size={14} />
            Submit Revision
          </button>
          <button
            onClick={handleCancel}
            className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-gray-800 hover:bg-gray-700
              text-sm text-gray-400 transition-colors"
          >
            <X size={14} />
            Cancel
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-3">
      <button
        onClick={approve}
        className="flex items-center gap-2 px-5 py-2.5 rounded-xl font-semibold text-sm
          bg-emerald-600 hover:bg-emerald-500 active:bg-emerald-700 transition-colors"
      >
        <ThumbsUp size={15} />
        Approve &amp; Generate Report
      </button>
      <button
        onClick={() => setMode('revise')}
        className="flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-medium
          bg-gray-800 hover:bg-gray-700 text-gray-300 transition-colors"
      >
        <MessageSquare size={15} />
        Request Revision
      </button>
    </div>
  );
}
