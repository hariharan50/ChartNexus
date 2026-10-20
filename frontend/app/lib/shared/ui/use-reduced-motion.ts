import { useEffect, useState } from 'react';

const QUERY = '(prefers-reduced-motion: reduce)';

/**
 * Whether the visitor has asked for reduced motion.
 *
 * CSS can read this on its own — `app.css` has a global block that flattens
 * every transition and animation duration — so this hook is only for the motion
 * a stylesheet cannot reach: the chart libraries, which animate inside their
 * own canvas/SVG surfaces.
 *
 * Starts `false` and corrects after mount rather than guessing during SSR.
 * `matchMedia` does not exist on the server, and a chart renders no data until
 * it has a browser anyway, so there is nothing to mismatch — the first paint
 * that could animate is already a client paint.
 *
 * Subscribed rather than read once: the preference can change while the app is
 * open, and someone turning it on mid-session is exactly the person who most
 * needs it to take effect without a reload.
 */
export function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);

  useEffect(() => {
    const mql = window.matchMedia?.(QUERY);
    if (!mql) return;
    setReduced(mql.matches);
    const onChange = (event: MediaQueryListEvent) => setReduced(event.matches);
    mql.addEventListener('change', onChange);
    return () => mql.removeEventListener('change', onChange);
  }, []);

  return reduced;
}
