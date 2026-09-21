import { describe, expect, it } from 'vitest';
import type { BuildupState, FuturesRow } from '../../app/lib/contexts/futures-analytics/types';
import {
  applyFilter,
  clockLabel,
  expiryLabel,
  filterCounts,
  HEATMAP_FILTERS
} from '../../app/routes/terminal/future-lab/heatmap-data';

/** The Future Heatmap's chip row: what each filter selects, and what it counts. */

function row(
  symbol: string,
  {
    price = '1',
    oi = '1',
    state = 'long_buildup'
  }: { price?: string | null; oi?: string | null; state?: BuildupState } = {}
): FuturesRow {
  return {
    symbol,
    name: symbol,
    price: '100',
    price_change_percent: price,
    open_interest: 1000,
    oi_change_percent: oi,
    state,
    kind: 'stock',
    lot_size: 1,
    volume: 10,
    volume_change_percent: '1',
    open_marker: null,
    sector: 'IT'
  };
}

const BOARD: FuturesRow[] = [
  row('UP', { price: '1.5', oi: '2', state: 'long_buildup' }),
  row('DOWN', { price: '-1.5', oi: '2', state: 'short_buildup' }),
  row('UPOUT', { price: '1.5', oi: '-2', state: 'short_covering' }),
  row('DOWNOUT', { price: '-1.5', oi: '-2', state: 'long_unwinding' }),
  row('FLAT', { price: '0', oi: '0', state: 'neutral' }),
  row('UNKNOWN', { price: null, oi: null, state: 'neutral' })
];

describe('heatmap filters', () => {
  it('shows everything under All', () => {
    expect(applyFilter(BOARD, 'all')).toHaveLength(BOARD.length);
  });

  it('splits gainers and losers by price direction', () => {
    expect(applyFilter(BOARD, 'gainers').map((r) => r.symbol)).toEqual(['UP', 'UPOUT']);
    expect(applyFilter(BOARD, 'losers').map((r) => r.symbol)).toEqual(['DOWN', 'DOWNOUT']);
  });

  it('splits OI gainers and losers by open-interest direction', () => {
    expect(applyFilter(BOARD, 'oi_gainers').map((r) => r.symbol)).toEqual(['UP', 'DOWN']);
    expect(applyFilter(BOARD, 'oi_losers').map((r) => r.symbol)).toEqual(['UPOUT', 'DOWNOUT']);
  });

  it('selects each build-up state', () => {
    expect(applyFilter(BOARD, 'long_buildup').map((r) => r.symbol)).toEqual(['UP']);
    expect(applyFilter(BOARD, 'short_buildup').map((r) => r.symbol)).toEqual(['DOWN']);
    expect(applyFilter(BOARD, 'short_covering').map((r) => r.symbol)).toEqual(['UPOUT']);
    expect(applyFilter(BOARD, 'long_unwinding').map((r) => r.symbol)).toEqual(['DOWNOUT']);
  });

  it('leaves unchanged and unmeasured contracts out of both halves', () => {
    // Gainers and losers are directions, not a partition — a contract that did
    // not move belongs to neither, and one we could not measure to nothing.
    const counts = filterCounts(BOARD);

    expect(counts.gainers + counts.losers).toBe(BOARD.length - 2);
    expect(counts.oi_gainers + counts.oi_losers).toBe(BOARD.length - 2);
  });

  it('counts every chip over the whole board', () => {
    const counts = filterCounts(BOARD);

    expect(counts.all).toBe(BOARD.length);
    for (const filter of HEATMAP_FILTERS) {
      expect(counts[filter.id]).toBe(applyFilter(BOARD, filter.id).length);
    }
  });

  it('counts nothing when the board is empty rather than throwing', () => {
    const counts = filterCounts([]);

    expect(Object.values(counts).every((n) => n === 0)).toBe(true);
  });
});

describe('expiryLabel', () => {
  const now = new Date('2026-09-21T06:00:00Z'); // 11:30 IST

  it('reads as the contract plus days remaining', () => {
    expect(expiryLabel('2026-09-29', now)).toBe('29 Sep 2026 (8d)');
  });

  it('counts the days in exchange-local time', () => {
    // 20:00 UTC on the 21st is already the 22nd in IST, so an expiry on the
    // 29th is a day closer than a UTC reading would suggest.
    expect(expiryLabel('2026-09-29', new Date('2026-09-21T20:00:00Z'))).toBe('29 Sep 2026 (7d)');
  });

  it('drops the countdown once the contract is past', () => {
    expect(expiryLabel('2026-09-01', now)).toBe('01 Sep 2026');
  });

  it('falls back when the API sent no expiry', () => {
    expect(expiryLabel(null, now)).toBe('Front month');
    expect(expiryLabel('not-a-date', now)).toBe('Front month');
  });
});

describe('clockLabel', () => {
  it('spells the month the same way the expiry chip does', () => {
    // The two sit inches apart in the header. en-GB renders September as
    // "Sept", so a clock formatted independently read "21 Sept" beside a chip
    // reading "29 Sep" — one of them looked broken.
    const now = new Date('2026-09-21T06:00:00Z');

    expect(clockLabel(now)).toContain('21 Sep 2026');
    expect(expiryLabel('2026-09-29', now)).toContain('29 Sep 2026');
  });

  it('reads the wall clock in exchange-local time', () => {
    // 06:00 UTC is 11:30 IST, not 06:00.
    expect(clockLabel(new Date('2026-09-21T06:00:00Z'))).toBe('21 Sep 2026, 11:30:00 am');
  });

  it('rolls the date over at IST midnight, not UTC', () => {
    expect(clockLabel(new Date('2026-09-21T20:00:00Z'))).toBe('22 Sep 2026, 01:30:00 am');
  });
});
