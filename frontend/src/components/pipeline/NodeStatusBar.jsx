import { CheckCircle2, Loader2, Circle } from 'lucide-react';
import { usePipelineContext } from '../../context/PipelineContext';

const STATUS_CONFIG = {
  pending:  {
    Icon:        Circle,
    iconClass:   'text-gray-700',
    labelClass:  'text-gray-600',
    lineClass:   'bg-gray-800',
    spin:        false,
  },
  running:  {
    Icon:        Loader2,
    iconClass:   'text-indigo-400',
    labelClass:  'text-indigo-300 font-semibold',
    lineClass:   'bg-indigo-900',
    spin:        true,
  },
  complete: {
    Icon:        CheckCircle2,
    iconClass:   'text-green-400',
    labelClass:  'text-green-400',
    lineClass:   'bg-green-800',
    spin:        false,
  },
};

export default function NodeStatusBar() {
  const { state } = usePipelineContext();

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl px-6 py-5">
      <div className="flex items-start">
        {state.nodes.map((node, idx) => {
          const { Icon, iconClass, labelClass, lineClass, spin } = STATUS_CONFIG[node.status];
          const isLast = idx === state.nodes.length - 1;

          return (
            <div key={node.name} className="flex items-center flex-1 min-w-0">
              {/* Step indicator */}
              <div className="flex flex-col items-center gap-1.5 shrink-0">
                <Icon
                  size={20}
                  className={`${iconClass} transition-colors duration-300 ${spin ? 'animate-spin' : ''}`}
                />
                <span className={`text-xs whitespace-nowrap transition-colors duration-300 ${labelClass}`}>
                  {node.displayName}
                </span>
              </div>

              {/* Connector line */}
              {!isLast && (
                <div
                  className={`flex-1 h-px mx-3 -mt-5 transition-colors duration-500 ${lineClass}`}
                />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
