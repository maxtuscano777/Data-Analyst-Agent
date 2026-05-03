import { useEffect } from 'react';

/**
 * Automatically scrolls a container ref to its bottom whenever `deps` changes.
 * Pass the logs array (or its length) as deps so the terminal scrolls on each
 * new log entry.
 */
export function useAutoScroll(ref, deps) {
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, deps); // eslint-disable-line react-hooks/exhaustive-deps
}
