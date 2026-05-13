import { useEffect } from 'react';

export function useAutoDismiss(
  value: string | null,
  clear: (value: null) => void,
  delayMs = 6000,
) {
  useEffect(() => {
    if (!value) return undefined;
    const timer = window.setTimeout(() => clear(null), delayMs);
    return () => window.clearTimeout(timer);
  }, [clear, delayMs, value]);
}
