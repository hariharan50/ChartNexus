import { describe, expect, it } from 'vitest';
import {
  buildRows,
  coverageNote,
  csvFilename,
  dailyBars,
  dayLabel,
  fmtIv,
  istDate,
  ivHvIvpCsv,
  ivPercentile,
  ivRank,
  logReturns,
  MIN_IV_OBSERVATIONS,
  rollingHv,
  rollingRv,
  SESSIONS_PER_YEAR,
  type DailyBar,
  type IvHistoryView,
  type IvSession
} from '../../app/routes/terminal/options/iv-hv-ivp/iv-hv-ivp-data';
import type { WireCandle } from '../../app/routes/terminal/analyse/analyse-data';

/**
 * Every number this page draws beyond the two raw payloads is computed here, so
 * these tests are the page. The cases that matter are the ones where a
 * statistic would look authoritative while being built from nothing: a window
 * that has not filled, a lookback of four sessions, a flat stretch with no range
 * to rank within.
 */

function bar(overrides: Partial<DailyBar> = {}): DailyBar {
  return { d: '2026-09-01', open: 100, high: 102, low: 98, close: 101, ...overrides };
}

/** A series whose closes alternate, so it has a known non-zero volatility. */
function zigzag(count: number, from = '2026-01-01'): DailyBar[] {
  const start = new Date(`${from}T00:00:00Z`);
  return Array.from({ length: count }, (_, index) => {
    const day = new Date(start.getTime() + index * 86_400_000).toISOString().slice(0, 10);
    const close = index % 2 === 0 ? 100 : 102;
    return { d: day, open: 100, high: Math.max(100, close) + 1, low: 99, close };
  });
}

describe('logReturns', () => {
  it('has no return on the first bar — there is nothing before it', () => {
    expect(logReturns([100, 110])[0]).toBeNull();
  });

  it('is the log of the ratio between consecutive closes', () => {
    expect(logReturns([100, 110])[1]).toBeCloseTo(Math.log(1.1));
  });

  it('breaks across a gap rather than spanning it', () => {
    expect(logReturns([100, null, 110])).toEqual([null, null, null]);
  });

  it('refuses a non-positive close, which has no logarithm', () => {
    expect(logReturns([0, 110])[1]).toBeNull();
  });
});

describe('rollingHv', () => {
  it('is null until the window has actually filled', () => {
    // A 21-day number computed from four days is not a 21-day number.
    const hv = rollingHv([100, 101, 102, 103, 104], 21);
    expect(hv.every((value) => value === null)).toBe(true);
  });

  it('annualises the daily deviation by the square root of the trading year', () => {
    // Constant 1% daily moves: zero deviation, so the vol is zero.
    const steady = [100, 101, 102.01, 103.0301, 104.060401];
    expect(rollingHv(steady, 3).at(-1)).toBeCloseTo(0, 6);
  });

  it('reports a real number once the window is covered', () => {
    const closes = zigzag(40).map((entry) => entry.close);
    const hv = rollingHv(closes, 10).at(-1);
    expect(hv).not.toBeNull();
    expect(hv!).toBeGreaterThan(0);
    // Sanity: annualisation must dominate, not vanish.
    expect(hv!).toBeGreaterThan(Math.sqrt(SESSIONS_PER_YEAR));
  });

  it('refuses a window that is mostly gaps', () => {
    const closes: (number | null)[] = [100, null, null, null, null, null, null, 101];
    expect(rollingHv(closes, 6).at(-1)).toBeNull();
  });
});

describe('rollingRv', () => {
  it('is null until the window has filled', () => {
    expect(rollingRv([bar(), bar()], 10).every((value) => value === null)).toBe(true);
  });

  it('scores a day that travelled and came back, which close-to-close calls flat', () => {
    // Open == close every day, so HV is zero; the range is not, so RV is not.
    const flat: DailyBar[] = Array.from({ length: 12 }, (_, index) => ({
      d: `2026-01-${String(index + 1).padStart(2, '0')}`,
      open: 100,
      high: 103,
      low: 97,
      close: 100
    }));
    expect(
      rollingHv(
        flat.map((entry) => entry.close),
        10
      ).at(-1)
    ).toBeCloseTo(0, 6);
    expect(rollingRv(flat, 10).at(-1)!).toBeGreaterThan(0);
  });

  it('never returns a NaN from a bar whose body exceeds its range', () => {
    const odd: DailyBar[] = Array.from({ length: 12 }, () => bar({ high: 100, low: 100 }));
    const rv = rollingRv(odd, 10).at(-1);
    expect(rv).not.toBeNull();
    expect(Number.isNaN(rv!)).toBe(false);
  });
});

describe('ivRank and ivPercentile', () => {
  const rising = Array.from({ length: 20 }, (_, index) => 10 + index);

  it('ranks today between the window low and high', () => {
    // Last value is the highest of the window, so the rank is 100.
    expect(ivRank(rising, 20).at(-1)).toBeCloseTo(100);
  });

  it('counts the sessions below today for the percentile', () => {
    // 19 of the 20 in the window sit below the last.
    expect(ivPercentile(rising, 20).at(-1)).toBeCloseTo((19 / 20) * 100);
  });

  it('is the difference between the two that matters on an outlier', () => {
    // One panic day pins the range; rank collapses, percentile barely moves.
    const spiked = [...Array.from({ length: 19 }, () => 12), 60, 13];
    const rank = ivRank(spiked, 21).at(-1)!;
    const percentile = ivPercentile(spiked, 21).at(-1)!;
    expect(rank).toBeLessThan(10);
    expect(percentile).toBeGreaterThan(90);
  });

  it('refuses to rank a lookback too thin to mean anything', () => {
    const few = Array.from({ length: MIN_IV_OBSERVATIONS - 1 }, (_, index) => 10 + index);
    expect(ivRank(few, 20).at(-1)).toBeNull();
    expect(ivPercentile(few, 20).at(-1)).toBeNull();
  });

  it('has no rank in a perfectly flat window — there is no range to sit in', () => {
    const flat = Array.from({ length: 20 }, () => 12);
    expect(ivRank(flat, 20).at(-1)).toBeNull();
    // Percentile still answers: nothing sat below today.
    expect(ivPercentile(flat, 20).at(-1)).toBe(0);
  });

  it('ignores sessions with no reading rather than treating them as zero', () => {
    const gappy = [...Array.from({ length: 12 }, () => 12), null, 20];
    expect(ivRank(gappy, 20).at(-1)).toBeCloseTo(100);
  });
});

describe('dailyBars', () => {
  const candle = (time: string, close: number): WireCandle => ({
    time,
    open: 100,
    high: 105,
    low: 95,
    close,
    volume: 1
  });

  it('maps an instant to the IST trading date it belongs to', () => {
    // 20:00 UTC is 01:30 the next day in IST.
    expect(istDate('2026-09-02T20:00:00Z')).toBe('2026-09-03');
    expect(istDate('2026-09-02T06:00:00Z')).toBe('2026-09-02');
  });

  it('collapses two bars on one IST date, keeping the last close and the true range', () => {
    const bars = dailyBars([
      candle('2026-09-02T04:00:00Z', 100),
      { ...candle('2026-09-02T09:00:00Z', 110), high: 120, low: 90 }
    ]);
    expect(bars).toHaveLength(1);
    expect(bars[0]!.close).toBe(110);
    expect(bars[0]!.high).toBe(120);
    expect(bars[0]!.low).toBe(90);
  });

  it('returns the sessions oldest first', () => {
    const bars = dailyBars([candle('2026-09-03T04:00:00Z', 1), candle('2026-09-01T04:00:00Z', 2)]);
    expect(bars.map((entry) => entry.d)).toEqual(['2026-09-01', '2026-09-03']);
  });
});

describe('buildRows', () => {
  const bars = zigzag(30, '2026-08-01');
  const sessions: IvSession[] = bars.slice(-5).map((entry, index) => ({
    d: entry.d,
    iv: 11 + index,
    future_close: 24_650,
    captures: 100
  }));

  it('keeps the price spine and joins IV onto it', () => {
    // The whole point of the page: a short IV history inside a long price one,
    // rather than the price truncated to match.
    const rows = buildRows(bars, sessions, { hvWindow: 10, ivWindow: 20 });
    expect(rows).toHaveLength(bars.length);
    expect(rows.filter((row) => row.iv !== null)).toHaveLength(5);
    expect(rows[0]!.iv).toBeNull();
    expect(rows.at(-1)!.iv).toBe(15);
  });

  it('carries a close on every row', () => {
    const rows = buildRows(bars, sessions, { hvWindow: 10, ivWindow: 20 });
    expect(rows.every((row) => row.close !== null)).toBe(true);
  });

  it('leaves IVR and IVP blank while the IV history is too short to rank', () => {
    const rows = buildRows(bars, sessions, { hvWindow: 10, ivWindow: 20 });
    expect(rows.every((row) => row.ivr === null)).toBe(true);
    expect(rows.every((row) => row.ivp === null)).toBe(true);
  });

  it('is empty when there are no price bars, whatever IV exists', () => {
    expect(buildRows([], sessions, { hvWindow: 10, ivWindow: 20 })).toEqual([]);
  });
});

describe('coverageNote', () => {
  const view = (covered: number): IvHistoryView => ({
    instrument_id: 'NIFTY',
    symbol: 'NIFTY',
    requested_days: 365,
    covered_sessions: covered,
    start: '2025-09-03',
    end: '2026-09-03',
    sessions: []
  });

  it('says nothing when the history covers the window', () => {
    expect(coverageNote(view(252), 252)).toBeNull();
  });

  it('names an archive that has not started yet', () => {
    expect(coverageNote(view(0), 252)).toContain('No implied-volatility history');
  });

  it('explains why the rank is blank when there are too few sessions', () => {
    const note = coverageNote(view(4), 252);
    expect(note).toContain('4 sessions');
    expect(note).toContain(String(MIN_IV_OBSERVATIONS));
  });

  it('says the lookback is short rather than letting it pass for a year', () => {
    expect(coverageNote(view(30), 252)).toContain('30 sessions');
  });
});

describe('formatting and export', () => {
  it('quotes volatility to two decimals, as the reference does', () => {
    expect(fmtIv(11.3149)).toBe('11.31');
  });

  it('names a date the way the axis and tooltip do', () => {
    expect(dayLabel('2026-07-30')).toBe('30 Jul 26');
  });

  it('exports one row per session, blanking what was never computed', () => {
    const rows = [
      { d: '2026-09-01', close: 100, iv: 12, hv: null, rv: null, ivr: null, ivp: null }
    ];
    expect(ivHvIvpCsv(rows).split('\n')).toEqual([
      'date,close,iv,hv,rv,ivr,ivp',
      '2026-09-01,100,12,,,,'
    ]);
  });

  it('names the download after the session it ends on', () => {
    const rows = [
      { d: '2026-09-03', close: 1, iv: null, hv: null, rv: null, ivr: null, ivp: null }
    ];
    expect(csvFilename('NIFTY', rows)).toBe('iv-hv-ivp-NIFTY-2026-09-03.csv');
    expect(csvFilename('NIFTY', [])).toBe('iv-hv-ivp-NIFTY.csv');
  });
});
