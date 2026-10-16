/**
 * Turning the catalog into something a picker can show, and deciding where a
 * chosen symbol goes.
 *
 * This logic began on Future Lab → Price vs OI, which was the first page to
 * face the full ~219-contract universe rather than a hardcoded three. The
 * header search needs exactly the same ranking, so it lives here rather than
 * being imported out of a route folder — `price-vs-oi-data.ts` re-exports it,
 * so that page and its tests are unchanged.
 */

import type { InstrumentKind } from './types';

/** One row in a picker, derived from the catalog rather than hardcoded. */
export interface PickerEntry {
  symbol: string;
  name: string;
  /** Two or three characters for the badge — the catalog has no logos. */
  badge: string;
}

/**
 * Narrow the universe to what someone typed.
 *
 * Symbol matches sort ahead of name matches, and a prefix ahead of a
 * mid-string hit: typing "TCS" should not bury the contract called TCS under
 * every company whose description happens to contain it.
 */
export function filterInstruments(
  entries: PickerEntry[],
  search: string,
  limit = 60
): PickerEntry[] {
  const needle = search.trim().toUpperCase();
  if (!needle) return entries.slice(0, limit);

  const scored: { entry: PickerEntry; rank: number }[] = [];
  for (const entry of entries) {
    const symbol = entry.symbol.toUpperCase();
    const name = entry.name.toUpperCase();
    if (symbol === needle) scored.push({ entry, rank: 0 });
    else if (symbol.startsWith(needle)) scored.push({ entry, rank: 1 });
    else if (symbol.includes(needle)) scored.push({ entry, rank: 2 });
    else if (name.startsWith(needle)) scored.push({ entry, rank: 3 });
    else if (name.includes(needle)) scored.push({ entry, rank: 4 });
  }
  scored.sort((a, b) => a.rank - b.rank || a.entry.symbol.localeCompare(b.entry.symbol));
  return scored.slice(0, limit).map((hit) => hit.entry);
}

/** An index sits at the top of the list; the stocks follow alphabetically. */
export function toPickerEntries(
  rows: { symbol: string; name: string; kind: string }[]
): PickerEntry[] {
  return [...rows]
    .sort((a, b) => {
      if (a.kind !== b.kind) return a.kind === 'index' ? -1 : 1;
      return a.symbol.localeCompare(b.symbol);
    })
    .map((row) => ({ symbol: row.symbol, name: row.name, badge: badgeFor(row.symbol) }));
}

function badgeFor(symbol: string): string {
  // The leading letters, not an abbreviation anyone has to learn: two of them
  // fit the circle at every symbol length, and the full ticker sits beside it.
  return symbol
    .replace(/[^A-Z0-9]/gi, '')
    .slice(0, 2)
    .toUpperCase();
}

// -- where a symbol goes -----------------------------------------------------

/** Price vs OI for the option chain — indices, whose chains are what traders read. */
export const OPTIONS_PRICE_VS_OI = '/options/price-vs-oi';
/** Price vs OI for the future itself — the view that covers the whole universe. */
export const FUTURES_PRICE_VS_OI = '/future-lab/price-vs-oi';

/**
 * Where picking a symbol takes you.
 *
 * The two Price vs OI pages answer different questions, and which one is the
 * useful answer depends on what was picked. An index gets the Options Lab
 * view, where the OI line sums the whole chain. A stock gets Future Lab, which
 * charts the front-month future against that contract's own open interest —
 * the Options Lab page is wired to three hardcoded indices and would have
 * nothing to say about ITC.
 *
 * One function so the rule is in one place: the header search, and anything
 * that later wants to deep-link a symbol, must not each decide this for
 * themselves.
 */
export function destinationFor(instrument: { symbol: string; kind: InstrumentKind }): string {
  const page = instrument.kind === 'index' ? OPTIONS_PRICE_VS_OI : FUTURES_PRICE_VS_OI;
  return `${page}?symbol=${encodeURIComponent(instrument.symbol)}`;
}
