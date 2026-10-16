/**
 * The instrument every analytics page charts.
 *
 * Two sources, in this order:
 *
 * 1. **`?symbol=` in the URL.** A link has to open on what its sender meant,
 *    so a param always wins — over the reader's own remembered choice included.
 * 2. **The remembered choice** (`useInstrumentStore`), so walking from Open
 *    Interest to Max Pain keeps you on ITC instead of snapping back to NIFTY,
 *    and so does coming back tomorrow.
 *
 * Choosing writes both: the URL so the page is linkable, the store so the next
 * page knows. `replace: true` because changing instrument refines the view
 * rather than making a new destination — twenty cycler clicks should not be
 * twenty entries in the back button.
 */

import { useCallback, useEffect } from 'react';
import { useSearchParams } from 'react-router';
import { DEFAULT_INSTRUMENT } from '$shared/config/instruments';
import { useInstrumentStore } from '$shared/ui/instrument-store';
import { SYMBOL_PARAM } from './use-symbol-param';

export function useSelectedInstrument(): [string, (next: string) => void] {
  const [params, setParams] = useSearchParams();
  const stored = useInstrumentStore((state) => state.symbol);
  const remember = useInstrumentStore((state) => state.setSymbol);

  const fromUrl = params.get(SYMBOL_PARAM)?.trim().toUpperCase();
  const symbol = fromUrl || stored || DEFAULT_INSTRUMENT;

  const select = useCallback(
    (next: string) => {
      const value = next.trim().toUpperCase();
      if (!value) return;
      remember(value);
      setParams(
        (current) => {
          const updated = new URLSearchParams(current);
          updated.set(SYMBOL_PARAM, value);
          return updated;
        },
        { replace: true }
      );
    },
    [remember, setParams]
  );

  // Put the remembered symbol in the URL when the page was opened without one,
  // so what is on screen and what a reader would copy out of the address bar
  // are the same thing. Runs after hydration, which is when the store has read
  // localStorage — doing it during render would make the server and the first
  // client render disagree.
  useEffect(() => {
    if (fromUrl) return;
    if (symbol === DEFAULT_INSTRUMENT) return;
    setParams(
      (current) => {
        const updated = new URLSearchParams(current);
        updated.set(SYMBOL_PARAM, symbol);
        return updated;
      },
      { replace: true }
    );
  }, [fromUrl, symbol, setParams]);

  return [symbol, select];
}
