import { describe, expect, it } from 'vitest';
import {
  clampCursor,
  filterInstruments,
  sliceTo,
  toPickerEntries,
  type PickerEntry
} from '../../app/routes/terminal/future-lab/price-vs-oi-data';

/** The Future Lab Price vs OI page's own logic: its picker and its replay. */

const CATALOG = [
  { symbol: 'RELIANCE', name: 'RELIANCE INDUSTRIES LTD', kind: 'stock' },
  { symbol: 'NIFTY', name: 'NIFTY50', kind: 'index' },
  { symbol: 'TCS', name: 'TATA CONSULTANCY SERVICES', kind: 'stock' },
  { symbol: 'BANKNIFTY', name: 'NIFTYBANK', kind: 'index' },
  { symbol: 'M&M', name: 'MAHINDRA & MAHINDRA LTD', kind: 'stock' }
];

describe('toPickerEntries', () => {
  it('lists the indices before the stocks', () => {
    // Six indices among 219 contracts would otherwise be lost alphabetically.
    const entries = toPickerEntries(CATALOG);

    expect(entries.slice(0, 2).map((e) => e.symbol)).toEqual(['BANKNIFTY', 'NIFTY']);
  });

  it('sorts each group alphabetically', () => {
    const stocks = toPickerEntries(CATALOG).slice(2);

    expect(stocks.map((e) => e.symbol)).toEqual(['M&M', 'RELIANCE', 'TCS']);
  });

  it('builds a badge that survives a punctuated ticker', () => {
    // M&M must not produce "M&" — the ampersand is not a letter anyone reads
    // as an abbreviation.
    const mm = toPickerEntries(CATALOG).find((e) => e.symbol === 'M&M');

    expect(mm?.badge).toBe('MM');
  });

  it('does not mutate the catalog it was handed', () => {
    const original = CATALOG.map((row) => row.symbol);

    toPickerEntries(CATALOG);

    expect(CATALOG.map((row) => row.symbol)).toEqual(original);
  });
});

describe('filterInstruments', () => {
  const entries: PickerEntry[] = toPickerEntries(CATALOG);

  it('shows everything when nothing is typed', () => {
    expect(filterInstruments(entries, '')).toHaveLength(entries.length);
  });

  it('puts an exact symbol match first', () => {
    // "TCS" also appears inside no other symbol here, but the ranking is what
    // stops a company description burying the contract of that name.
    expect(filterInstruments(entries, 'TCS')[0]?.symbol).toBe('TCS');
  });

  it('ranks a symbol prefix above a name match', () => {
    const hits = filterInstruments(entries, 'NIFTY').map((e) => e.symbol);

    // NIFTY and BANKNIFTY match on symbol; NIFTY's prefix wins over
    // BANKNIFTY's mid-string hit, and over NIFTYBANK matching only by name.
    expect(hits[0]).toBe('NIFTY');
  });

  it('matches company names too', () => {
    expect(filterInstruments(entries, 'MAHINDRA').map((e) => e.symbol)).toEqual(['M&M']);
  });

  it('ignores case and surrounding space', () => {
    expect(filterInstruments(entries, '  reliance ').map((e) => e.symbol)).toEqual(['RELIANCE']);
  });

  it('returns nothing rather than everything when nothing matches', () => {
    expect(filterInstruments(entries, 'DOGECOIN')).toEqual([]);
  });

  it('caps the list so the sidebar cannot be flooded', () => {
    const many = Array.from({ length: 200 }, (_, i) => ({
      symbol: `SYM${i}`,
      name: `Company ${i}`,
      kind: 'stock'
    }));

    expect(filterInstruments(toPickerEntries(many), '', 60)).toHaveLength(60);
  });
});

describe('replay cursor', () => {
  it('clamps to the last captured frame', () => {
    // Winding past the end would show a future the archive does not contain.
    expect(clampCursor(99, 10)).toBe(9);
  });

  it('clamps below zero', () => {
    expect(clampCursor(-5, 10)).toBe(0);
  });

  it('stays at zero for an empty session rather than going negative', () => {
    expect(clampCursor(3, 0)).toBe(0);
  });

  it('shows the whole series when not replaying', () => {
    const values = [1, 2, 3, 4];

    expect(sliceTo(values, null)).toEqual(values);
  });

  it('shows the session up to and including the cursor', () => {
    expect(sliceTo([1, 2, 3, 4], 1)).toEqual([1, 2]);
  });

  it('never slices past the end', () => {
    expect(sliceTo([1, 2, 3], 99)).toEqual([1, 2, 3]);
  });

  it('keeps the three series the same length at every position', () => {
    // The chart pairs them by index; a shorter OI array would silently shift
    // every open-interest reading onto the wrong timestamp.
    const t = ['a', 'b', 'c', 'd'];
    const price = [1, 2, 3, 4];
    const oi = [10, null, 30, 40];

    for (const cursor of [0, 1, 2, 3]) {
      expect(sliceTo(t, cursor)).toHaveLength(cursor + 1);
      expect(sliceTo(price, cursor)).toHaveLength(cursor + 1);
      expect(sliceTo(oi, cursor)).toHaveLength(cursor + 1);
    }
  });

  it('carries open-interest gaps through a slice rather than dropping them', () => {
    expect(sliceTo([10, null, 30], 2)).toEqual([10, null, 30]);
  });
});
