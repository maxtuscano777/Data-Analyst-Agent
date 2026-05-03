import { TrendingUp } from 'lucide-react';

function r2Color(r2) {
  if (r2 >= 0.7) return 'text-emerald-400';
  if (r2 >= 0.4) return 'text-amber-400';
  return 'text-red-400';
}

function r2Badge(r2) {
  if (r2 >= 0.7) return 'bg-emerald-950/60 text-emerald-400 border border-emerald-800';
  if (r2 >= 0.4) return 'bg-amber-950/60 text-amber-400 border border-amber-800';
  return 'bg-red-950/60 text-red-400 border border-red-800';
}

function r2Label(r2) {
  if (r2 >= 0.7) return 'Strong';
  if (r2 >= 0.4) return 'Moderate';
  return 'Weak';
}

export default function ModelEvalTable({ evaluations }) {
  if (!evaluations || evaluations.length === 0) return null;

  return (
    <div>
      <h3 className="flex items-center gap-2 text-sm font-semibold text-gray-300 mb-3">
        <TrendingUp size={15} className="text-emerald-400" />
        Model Performance <span className="text-gray-600 font-normal">(5-fold CV)</span>
      </h3>
      <div className="overflow-x-auto rounded-lg border border-gray-800">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-800 bg-gray-800/40">
              <th className="text-left px-4 py-2.5 text-xs font-medium text-gray-500 uppercase tracking-wider">
                Model
              </th>
              <th className="text-left px-4 py-2.5 text-xs font-medium text-gray-500 uppercase tracking-wider">
                CV R² Mean
              </th>
              <th className="text-left px-4 py-2.5 text-xs font-medium text-gray-500 uppercase tracking-wider">
                Std Dev
              </th>
              <th className="text-left px-4 py-2.5 text-xs font-medium text-gray-500 uppercase tracking-wider">
                Assessment
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800/60">
            {evaluations.map((ev, i) => (
              <tr key={i} className="hover:bg-gray-800/20 transition-colors">
                <td className="px-4 py-3 font-mono text-xs text-gray-200">
                  {ev.model_name}
                </td>
                <td className={`px-4 py-3 font-semibold tabular-nums ${r2Color(ev.cv_r2_mean)}`}>
                  {ev.cv_r2_mean.toFixed(3)}
                </td>
                <td className="px-4 py-3 text-gray-500 tabular-nums">
                  ±{ev.cv_r2_std.toFixed(3)}
                </td>
                <td className="px-4 py-3">
                  <span className={`text-xs px-2 py-0.5 rounded-full ${r2Badge(ev.cv_r2_mean)}`}>
                    {r2Label(ev.cv_r2_mean)}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
