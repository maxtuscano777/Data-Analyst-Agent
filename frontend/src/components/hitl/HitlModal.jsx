import { Eye } from 'lucide-react';
import { usePipelineContext } from '../../context/PipelineContext';
import ChartGallery from '../shared/ChartGallery';
import InsightsList from './InsightsList';
import ModelEvalTable from './ModelEvalTable';
import HitlActions from './HitlActions';

export default function HitlModal({ approve, revise }) {
  const { state } = usePipelineContext();
  const { hitl } = state;

  if (!hitl) return null;

  const hasModels = hitl.modelEvaluations && hitl.modelEvaluations.length > 0;
  const hasCharts = hitl.charts && hitl.charts.length > 0;

  return (
    <div className="fixed inset-0 bg-black/85 backdrop-blur-sm z-50 overflow-y-auto">
      <div className="min-h-full flex items-start justify-center px-4 py-8">
        <div className="bg-gray-900 border border-gray-800 rounded-2xl w-full max-w-4xl shadow-2xl">

          {/* Header */}
          <div className="sticky top-0 z-10 bg-gray-900/95 backdrop-blur border-b border-gray-800 px-6 py-5 rounded-t-2xl">
            <div className="flex items-start gap-3">
              <div className="p-2 rounded-lg bg-amber-950/50 border border-amber-800/50 shrink-0">
                <Eye size={18} className="text-amber-400" />
              </div>
              <div>
                <h2 className="text-base font-semibold text-gray-100">
                  Human Review Checkpoint
                </h2>
                <p className="text-sm text-gray-500 mt-0.5">
                  Review the draft analysis before generating the final executive report.
                </p>
              </div>
            </div>
          </div>

          {/* Body */}
          <div className="px-6 py-6 space-y-8">
            {/* Draft charts */}
            {hasCharts && (
              <section className="space-y-3">
                <h3 className="text-sm font-semibold text-gray-300">Draft Charts</h3>
                <ChartGallery charts={hitl.charts} />
              </section>
            )}

            {/* Insights */}
            {hitl.insights && hitl.insights.length > 0 && (
              <section className="bg-gray-800/30 border border-gray-800 rounded-xl p-5">
                <InsightsList insights={hitl.insights} />
              </section>
            )}

            {/* Model evaluations */}
            {hasModels && (
              <section>
                <ModelEvalTable evaluations={hitl.modelEvaluations} />
              </section>
            )}
          </div>

          {/* Sticky action footer */}
          <div className="sticky bottom-0 bg-gray-900/95 backdrop-blur border-t border-gray-800 px-6 py-5 rounded-b-2xl">
            <HitlActions approve={approve} revise={revise} />
          </div>

        </div>
      </div>
    </div>
  );
}
