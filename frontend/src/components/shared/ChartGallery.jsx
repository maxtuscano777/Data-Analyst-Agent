import { useState } from 'react';
import { ImageOff } from 'lucide-react';

function ChartImage({ url }) {
  const [errored, setErrored] = useState(false);
  const label = url.split('/').pop()?.replace(/\.png$/i, '').replaceAll('_', ' ') ?? 'Chart';

  if (errored) {
    return (
      <div className="flex flex-col items-center justify-center gap-2 rounded-xl border border-gray-800 bg-gray-900 p-8 text-center min-h-40">
        <ImageOff size={24} className="text-gray-700" />
        <span className="text-xs text-gray-600">{label}</span>
      </div>
    );
  }

  return (
    <figure className="rounded-xl overflow-hidden border border-gray-800 bg-white">
      <img
        src={url}
        alt={label}
        onError={() => setErrored(true)}
        className="w-full object-contain"
      />
      <figcaption className="bg-gray-950 px-3 py-1.5 text-xs text-gray-500 text-center capitalize">
        {label}
      </figcaption>
    </figure>
  );
}

export default function ChartGallery({ charts }) {
  if (!charts || charts.length === 0) return null;

  return (
    <div className={`grid gap-4 ${charts.length === 1 ? 'grid-cols-1' : 'grid-cols-1 md:grid-cols-2'}`}>
      {charts.map((url, i) => (
        <ChartImage key={`${url}-${i}`} url={url} />
      ))}
    </div>
  );
}
