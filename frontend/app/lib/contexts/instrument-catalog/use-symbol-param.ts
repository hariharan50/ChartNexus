/**
 * The charted symbol, held in the URL rather than in component state.
 *
 * Pages used to keep this in `useState`, which meant nothing could link to
 * them: the header search had no way to say "open Price vs OI on ITC", and a
 * reader who found something worth sharing could only send a URL that opens on
 * NIFTY. Putting it in the query string fixes all of that at once — the link
 * is shareable, the back button steps through symbols, and a reload stays
 * where it was.
 */

import { useCallback, useMemo } from 'react';
import { useSearchParams } from 'react-router';
import { DEFAULT_INSTRUMENT } from '$shared/config/instruments';

/** The query-string key. One spelling, so a link cannot miss by a letter. */
export const SYMBOL_PARAM = 'symbol';

/**
 * Read and write `?symbol=`.
 *
 * Normalised to upper case on the way in, because the catalog is keyed that
 * way and a hand-typed `?symbol=itc` should not miss.
 *
 * Writes `replace: true`: changing symbol inside a page is refining a view,
 * not a new destination, and stacking twenty history entries would turn the
 * back button into an undo log of every cycler click.
 */
export function useSymbolParam(
  fallback: string = DEFAULT_INSTRUMENT
): [string, (next: string) => void] {
  const [params, setParams] = useSearchParams();
  const raw = params.get(SYMBOL_PARAM);

  const symbol = useMemo(() => {
    const trimmed = raw?.trim().toUpperCase();
    return trimmed ? trimmed : fallback;
  }, [raw, fallback]);

  const setSymbol = useCallback(
    (next: string) => {
      const value = next.trim().toUpperCase();
      if (!value) return;
      setParams(
        (current) => {
          const updated = new URLSearchParams(current);
          updated.set(SYMBOL_PARAM, value);
          return updated;
        },
        { replace: true }
      );
    },
    [setParams]
  );

  return [symbol, setSymbol];
}
