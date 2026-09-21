/**
 * The handful of symbols the UI can name before the catalog has loaded.
 *
 * The tradeable universe is ~219 instruments served by `GET /instruments` and
 * read through `useInstruments()`. This module is emphatically *not* that list:
 * it exists only so a page can pick a sensible initial selection during
 * server-side render, when no query has resolved yet.
 *
 * It replaced nine hand-maintained copies of a three-instrument array scattered
 * across the route tree. If you are reaching for this to populate a picker, a
 * tab strip or a dropdown, reach for `useInstruments()` instead — otherwise the
 * duplication starts over.
 */

/** What a page charts when the user has expressed no preference. */
export const DEFAULT_INSTRUMENT = 'NIFTY';

/**
 * Initial selections for multi-pane layouts. The three headline indices, in the
 * order the terminal has always shown them.
 */
export const DEFAULT_INSTRUMENTS: readonly string[] = ['NIFTY', 'SENSEX', 'BANKNIFTY'];

/** The nth default, falling back to the first — for fixed-size pane grids. */
export function defaultInstrumentAt(index: number): string {
  return DEFAULT_INSTRUMENTS[index] ?? DEFAULT_INSTRUMENT;
}
