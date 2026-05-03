import { useRef, useState } from 'react';
import { Upload, X, FileText } from 'lucide-react';

export default function DropZone({ files, onFilesChange }) {
  const inputRef = useRef(null);
  const [isDragging, setIsDragging] = useState(false);

  const addFiles = (incoming) => {
    const csvs = Array.from(incoming).filter(
      (f) => f.type === 'text/csv' || f.name.endsWith('.csv')
    );
    if (!csvs.length) return;
    const existingNames = new Set(files.map((f) => f.name));
    onFilesChange([...files, ...csvs.filter((f) => !existingNames.has(f.name))]);
  };

  const removeFile = (name) => onFilesChange(files.filter((f) => f.name !== name));

  const onDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    addFiles(e.dataTransfer.files);
  };

  return (
    <div className="space-y-3">
      {/* Drop target */}
      <div
        role="button"
        tabIndex={0}
        onClick={() => inputRef.current.click()}
        onKeyDown={(e) => e.key === 'Enter' && inputRef.current.click()}
        onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={onDrop}
        className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors select-none
          ${isDragging
            ? 'border-indigo-500 bg-indigo-950/20'
            : 'border-gray-700 hover:border-gray-500 hover:bg-gray-800/30'
          }`}
      >
        <Upload size={28} className="mx-auto mb-3 text-gray-500" />
        <p className="text-sm font-medium text-gray-300">
          Drop CSV files here or <span className="text-indigo-400">click to browse</span>
        </p>
        <p className="text-xs text-gray-600 mt-1">Multiple files supported</p>
        <input
          ref={inputRef}
          type="file"
          accept=".csv,text/csv"
          multiple
          className="hidden"
          onChange={(e) => addFiles(e.target.files)}
        />
      </div>

      {/* File list */}
      {files.length > 0 && (
        <ul className="space-y-1.5">
          {files.map((f) => (
            <li
              key={f.name}
              className="flex items-center justify-between bg-gray-800/60 rounded-lg px-3 py-2"
            >
              <div className="flex items-center gap-2 min-w-0">
                <FileText size={14} className="text-indigo-400 shrink-0" />
                <span className="text-sm text-gray-200 truncate">{f.name}</span>
                <span className="text-xs text-gray-600 shrink-0">
                  {(f.size / 1024).toFixed(1)} KB
                </span>
              </div>
              <button
                onClick={(e) => { e.stopPropagation(); removeFile(f.name); }}
                className="ml-2 text-gray-600 hover:text-gray-300 transition-colors"
                aria-label={`Remove ${f.name}`}
              >
                <X size={14} />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
