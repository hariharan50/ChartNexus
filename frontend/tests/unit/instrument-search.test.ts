import { describe, expect, it } from 'vitest';
import {
  destinationFor,
  filterInstruments,
  toPickerEntries,
  type PickerEntry
} from '../../app/lib/contexts/instrument-catalog/search';

/**
 * Turning the catalog into picker rows, ranking a search over it, and deciding
 * where a chosen symbol goes.
 *
 * These moved out of the Future Lab page's tests when the header search came
 * to need the same ranking.
 */

const CATALOG = [
  { symbol: 'RELIANCE', name: 'RELIANCE INDUSTRIES LTD', kind: 'stock' },
  { symbol: 'NIFTY', name: 'NIFTY50', kind: 'index' },
  { symbol: 'TCS', name: 'TATA CONSULTANCY SERVICES', kind: 'stock' },
  { symbol: 'BANKNIFTY', name: 'NIFTYBANK', kind: 'index' },
  { symbol: 'M&M', name: 'MAHINDRA & MAHINDRA LTD', kind: 'stock' },
  { symbol: 'ITC', name: 'ITC LTD', kind: 'stock' },
  { symbol: 'ITCHOTELS', name: 'ITC HOTELS LTD', kind: 'stock' }
];

describe('toPickerEntries', () => {
  it('lists the indices before the stocks', () => {
    // Six indices among 219 contracts would otherwise be lost alphabetically.
    const entries = toPickerEntries(CATALOG);

    expect(entries.slice(0, 2).map((e) => e.symbol)).toEqual(['BANKNIFTY', 'NIFTY']);
  });

  it('sorts each group alphabetically', () => {
    const stocks = toPickerEntries(CATALOG).slice(2);

    expect(stocks.map((e) => e.symbol)).toEqual(['ITC', 'ITCHOTELS', 'M&M', 'RELIANCE', 'TCS']);
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

describe('searching for a ticker someone typed', () => {
  const entries: PickerEntry[] = toPickerEntries(CATALOG);

  it('puts ITC above ITCHOTELS', () => {
    // The case the header search exists for: an exact ticker outranks the
    // longer symbol that merely starts with it.
    const hits = filterInstruments(entries, 'ITC', 8).map((e) => e.symbol);

    expect(hits).toEqual(['ITC', 'ITCHOTELS']);
  });

  it('finds a stock by its company name', () => {
    expect(filterInstruments(entries, 'HOTELS', 8).map((e) => e.symbol)).toEqual(['ITCHOTELS']);
  });

  it('honours a dropdown-sized cap', () => {
    expect(filterInstruments(entries, 'I', 2)).toHaveLength(2);
  });
});

describe('destinationFor', () => {
  it('sends a stock to the futures view', () => {
    // The Options Lab page charts three hardcoded indices; it has nothing to
    // say about ITC, and the futures view covers the whole universe.
    expect(destinationFor({ symbol: 'ITC', kind: 'stock' })).toBe(
      '/future-lab/price-vs-oi?symbol=ITC'
    );
  });

  it('sends an index to the chain view', () => {
    expect(destinationFor({ symbol: 'NIFTY', kind: 'index' })).toBe(
      '/options/price-vs-oi?symbol=NIFTY'
    );
  });

  it('encodes a symbol that is not URL-safe', () => {
    // M&M would otherwise end the query string at the ampersand and arrive as
    // a bare "M" with a stray "M" parameter beside it.
    expect(destinationFor({ symbol: 'M&M', kind: 'stock' })).toBe(
      '/future-lab/price-vs-oi?symbol=M%26M'
    );
  });
});
