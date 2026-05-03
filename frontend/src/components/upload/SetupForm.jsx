import { LLM_MODELS } from '../../lib/constants';

const inputClass =
  'w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100 ' +
  'placeholder:text-gray-600 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors';

export default function SetupForm({
  userQuery, domainContext, llmModel,
  onUserQueryChange, onDomainContextChange, onLlmModelChange,
}) {
  return (
    <div className="space-y-4">
      {/* Business Goal */}
      <div>
        <label className="block text-sm font-medium text-gray-300 mb-1.5">
          Business Goal <span className="text-red-400">*</span>
        </label>
        <textarea
          value={userQuery}
          onChange={(e) => onUserQueryChange(e.target.value)}
          placeholder="e.g. Which product categories drive the most revenue? Are there delivery delay patterns that hurt customer satisfaction?"
          rows={3}
          className={`${inputClass} resize-none`}
        />
      </div>

      {/* Domain Context */}
      <div>
        <label className="block text-sm font-medium text-gray-300 mb-1.5">
          Domain Context{' '}
          <span className="text-gray-600 font-normal">(optional)</span>
        </label>
        <input
          type="text"
          value={domainContext}
          onChange={(e) => onDomainContextChange(e.target.value)}
          placeholder="e.g. Brazilian e-commerce marketplace"
          className={inputClass}
        />
      </div>

      {/* Model selector */}
      <div>
        <label className="block text-sm font-medium text-gray-300 mb-1.5">
          Model
        </label>
        <select
          value={llmModel}
          onChange={(e) => onLlmModelChange(e.target.value)}
          className={inputClass}
        >
          {LLM_MODELS.map((m) => (
            <option key={m.value} value={m.value}>
              {m.label}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}
