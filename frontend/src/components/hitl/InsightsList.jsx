import { Lightbulb } from 'lucide-react';

export default function InsightsList({ insights }) {
  if (!insights || insights.length === 0) return null;

  return (
    <div>
      <h3 className="flex items-center gap-2 text-sm font-semibold text-gray-300 mb-3">
        <Lightbulb size={15} className="text-amber-400" />
        Key Insights
      </h3>
      <ul className="space-y-2">
        {insights.map((insight, i) => (
          <li key={i} className="flex items-start gap-2.5 text-sm text-gray-300 leading-relaxed">
            <span className="text-indigo-400 mt-px shrink-0 font-bold">›</span>
            <span>{insight}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
