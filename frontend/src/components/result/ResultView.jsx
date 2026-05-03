import { BarChart3, CheckCircle2, RotateCcw } from 'lucide-react';
import { usePipelineContext } from '../../context/PipelineContext';
import ChartGallery from '../shared/ChartGallery';
import ExecutiveSummary from './ExecutiveSummary';

export default function ResultView() {
  const { state, dispatch } = usePipelineContext();
  const { result } = state;

  const hasCharts  = result?.finalChartPaths?.length > 0;
  const hasSummary = Boolean(result?.executiveSummaryMd);

  return (
    <div className="min-h-screen flex flex-col">
      {/* Header */}
      <header className="border-b border-gray-800 px-6 py-4 shrink-0">
        <div className="max-w-5xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <BarChart3 className="text-indigo-400" size={22} />
            <span className="font-semibold tracking-tight">ADAW — Analysis Complete</span>
          </div>
          <div className="flex items-center gap-3">
            <span className="flex items-center gap-1.5 text-xs text-emerald-400 font-medium">
              <CheckCircle2 size={13} />
              Pipeline complete
            </span>
            <button
              onClick={() => dispatch({ type: 'RESET' })}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-gray-800 hover:bg-gray-700
                text-xs text-gray-400 transition-colors"
            >
              <RotateCcw size={12} />
              New Analysis
            </button>
          </div>
        </div>
      </header>

      {/* Content */}
      <main className="flex-1 max-w-5xl mx-auto w-full px-6 py-8 space-y-10">
        {hasCharts && (
          <section>
            <h2 className="text-base font-semibold text-gray-200 mb-4">
              Final Charts
            </h2>
            <ChartGallery charts={result.finalChartPaths} />
          </section>
        )}

        {hasSummary && (
          <section>
            <h2 className="text-base font-semibold text-gray-200 mb-4">
              Executive Summary
            </h2>
            <ExecutiveSummary markdown={result.executiveSummaryMd} />
          </section>
        )}

        {!hasCharts && !hasSummary && (
          <div className="flex items-center justify-center py-20 text-gray-600 text-sm">
            No results available.
          </div>
        )}
      </main>
    </div>
  );
}
