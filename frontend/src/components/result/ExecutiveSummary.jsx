import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

export default function ExecutiveSummary({ markdown }) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-2xl px-8 py-8">
      <div
        className="
          prose prose-invert prose-sm max-w-none

          prose-headings:text-gray-100 prose-headings:font-semibold prose-headings:tracking-tight
          prose-h1:text-2xl prose-h1:mb-6
          prose-h2:text-lg prose-h2:mt-8 prose-h2:mb-3 prose-h2:border-b prose-h2:border-gray-800 prose-h2:pb-2
          prose-h3:text-base prose-h3:mt-6 prose-h3:mb-2

          prose-p:text-gray-300 prose-p:leading-7
          prose-strong:text-gray-100 prose-strong:font-semibold
          prose-em:text-gray-300

          prose-ul:text-gray-300 prose-ul:my-3
          prose-ol:text-gray-300 prose-ol:my-3
          prose-li:my-1 prose-li:leading-relaxed

          prose-table:text-sm
          prose-thead:border-b prose-thead:border-gray-700
          prose-th:text-gray-400 prose-th:font-medium prose-th:py-2 prose-th:px-3
          prose-td:text-gray-300 prose-td:py-2 prose-td:px-3 prose-td:border-b prose-td:border-gray-800

          prose-hr:border-gray-800 prose-hr:my-6

          prose-code:text-indigo-300 prose-code:bg-gray-800 prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded prose-code:text-xs prose-code:before:content-none prose-code:after:content-none
          prose-pre:bg-gray-800 prose-pre:border prose-pre:border-gray-700 prose-pre:rounded-xl

          prose-blockquote:border-l-indigo-500 prose-blockquote:text-gray-400
        "
      >
        <ReactMarkdown remarkPlugins={[remarkGfm]}>
          {markdown}
        </ReactMarkdown>
      </div>
    </div>
  );
}
