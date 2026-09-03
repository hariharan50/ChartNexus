import { describe, expect, it } from 'vitest';
import {
  buildSpreadRows,
  csvFilename,
  fetchDays,
  fmtSpread,
  ivHvCsv,
  MAX_FETCH_DAYS,
  spreadStats,
  trimToRange,
  warmupDays,
  type SpreadRow
} from '../../app/routes/terminal/options/iv-hv/iv-hv-data';
import type {
  DailyBar,
  IvSession
} from '../../app/routes/terminal/options/iv-hv-ivp/iv-hv-ivp-data';

/**
 * The page is one subtraction over two series the sibling page already derives,
 * so what these pin is the rule around the subtraction rather than the
 * arithmetic: a bar is drawn only where both halves are real. Every other case
 * here is a way that rule could be got wrong and still produce a number.
 */

/** A price series long enough for a 10-session HV window to fill. */
function bars(count: number, from = '2026-08-01'): DailyBar[] {
  const start = new Date(`${from}T00:00:00Z`);
  return Array.from({ length: count }, (_, index) => {
    const d = new Date(start.getTime() + index * 86_400_000).toISOString().slice(0, 10);
    const close = index % 2 === 0 ? 100 : 102;
    return { d, open: 100, high: 103, low: 99, close };
  });
}

function session(d: string, iv: number, future: number | null = 24_650): IvSession {
  return { d, iv, future_close: future, captures: 100 };
}

describe('buildSpreadRows', () => {
  it('keeps one row per price session, whatever IV exists', () => {
    const rows = buildSpreadRows(bars(20), [session('2026-08-15', 12)], 10);
    expect(rows).toHaveLength(20);
    expect(rows.every((row) => row.close !== null)).toBe(true);
  });

  it('subtracts the historical volatility from the implied one', () => {
    const price = bars(20);
    const day = price[15]!.d;
    const rows = buildSpreadRows(price, [session(day, 30)], 10);
    const row = rows.find((entry) => entry.d === day)!;

    expect(row.iv).toBe(30);
    expect(row.hv).not.toBeNull();
    expect(row.spread).toBeCloseTo(30 - row.hv!);
  });

  it('draws no bar on a session with no implied volatility', () => {
    // The historical half exists on every session; on its own it is not a
    // premium, and `0 - hv` would be a tall, confident, meaningless bar.
    const rows = buildSpreadRows(bars(20), [], 10);
    expect(rows.every((row) => row.spread === null)).toBe(true);
    expect(rows.at(-1)!.hv).not.toBeNull();
  });

  it('draws no bar before the HV window has filled, even with an IV', () => {
    const price = bars(20);
    const early = price[2]!.d;
    const rows = buildSpreadRows(price, [session(early, 12)], 10);
    const row = rows.find((entry) => entry.d === early)!;

    expect(row.iv).toBe(12);
    expect(row.hv).toBeNull();
    expect(row.spread).toBeNull();
  });

  it('carries the future close through on the sessions that recorded one', () => {
    const price = bars(20);
    const day = price[15]!.d;
    const rows = buildSpreadRows(price, [session(day, 12, 24_700)], 10);

    expect(rows.find((entry) => entry.d === day)!.future).toBe(24_700);
    expect(rows.find((entry) => entry.d === price[14]!.d)!.future).toBeNull();
  });

  it('leaves the future null on a stored session that never had one', () => {
    const price = bars(20);
    const day = price[15]!.d;
    const rows = buildSpreadRows(price, [session(day, 12, null)], 10);
    expect(rows.find((entry) => entry.d === day)!.future).toBeNull();
  });

  it('is empty with no price bars, whatever IV exists', () => {
    expect(buildSpreadRows([], [session('2026-08-15', 12)], 10)).toEqual([]);
  });

  it('ignores an IV session that has no matching price bar', () => {
    // A date the price series does not carry cannot be placed on the axis.
    const rows = buildSpreadRows(bars(20), [session('2030-01-01', 12)], 10);
    expect(rows.every((row) => row.iv === null)).toBe(true);
  });
});

describe('the HV warm-up', () => {
  it('asks for more history than it draws, by about the window', () => {
    // Without this the chart spends its whole range warming up: at a 1-month
    // range with a 1-month window, HV yields exactly one point.
    expect(fetchDays(30, 21)).toBeGreaterThan(30 + 21);
  });

  it('converts the window from sessions to calendar days', () => {
    // 21 sessions is about a calendar month, not three weeks.
    expect(warmupDays(21)).toBeGreaterThanOrEqual(30);
  });

  it('never asks for more than the endpoint serves', () => {
    expect(fetchDays(365, 126)).toBe(MAX_FETCH_DAYS);
  });

  it('actually yields a usable series once the warm-up is fetched', () => {
    // The regression this exists for, end to end: 21 sessions of range with a
    // 21-session window used to leave one bar.
    const price = bars(fetchDays(30, 21));
    const ivs = price.slice(-20).map((entry) => session(entry.d, 12));
    const rows = trimToRange(buildSpreadRows(price, ivs, 21), 30);

    expect(rows.length).toBeGreaterThan(15);
    expect(rows.filter((row) => row.spread !== null).length).toBeGreaterThan(15);
  });
});

describe('trimToRange', () => {
  it('keeps the requested span and drops the warm-up ahead of it', () => {
    const rows = bars(60).map((bar) => ({ d: bar.d }));
    const kept = trimToRange(rows, 30);
    expect(kept.length).toBeLessThan(rows.length);
    expect(kept.at(-1)).toEqual(rows.at(-1));
  });

  it('measures back from the newest session, not from today', () => {
    // A stale archive should still show its most recent stretch rather than an
    // empty window.
    const rows = bars(40, '2020-01-01').map((bar) => ({ d: bar.d }));
    expect(trimToRange(rows, 30).length).toBeGreaterThan(0);
  });

  it('leaves a series shorter than the range alone', () => {
    const rows = bars(5).map((bar) => ({ d: bar.d }));
    expect(trimToRange(rows, 30)).toHaveLength(5);
  });

  it('handles an empty series', () => {
    expect(trimToRange([], 30)).toEqual([]);
  });
});

describe('spreadStats', () => {
  const row = (spread: number | null): SpreadRow => ({
    d: '2026-08-15',
    spread,
    iv: 12,
    hv: 10,
    close: 100,
    future: null
  });

  it('counts each side of zero and averages the premium', () => {
    const stats = spreadStats([row(2), row(4), row(-3)]);
    expect(stats).toEqual({ covered: 3, rich: 2, cheap: 1, mean: 1 });
  });

  it('counts a session at exactly zero as neither rich nor cheap', () => {
    // Folding it into one side would overstate that side.
    const stats = spreadStats([row(0), row(2)]);
    expect(stats.covered).toBe(2);
    expect(stats.rich).toBe(1);
    expect(stats.cheap).toBe(0);
  });

  it('ignores sessions with no premium rather than counting them as zero', () => {
    const stats = spreadStats([row(4), row(null), row(null)]);
    expect(stats.covered).toBe(1);
    expect(stats.mean).toBe(4);
  });

  it('has no mean at all when nothing is computable', () => {
    expect(spreadStats([row(null)])).toEqual({ covered: 0, rich: 0, cheap: 0, mean: null });
    expect(spreadStats([])).toEqual({ covered: 0, rich: 0, cheap: 0, mean: null });
  });
});

describe('fmtSpread', () => {
  it('always shows the sign, because the sign is the reading', () => {
    expect(fmtSpread(4.66)).toBe('+4.66');
    expect(fmtSpread(-1.2)).toBe('−1.20');
  });

  it('uses a real minus sign, not a hyphen', () => {
    expect(fmtSpread(-1.2).startsWith('−')).toBe(true);
  });

  it('gives exact zero no sign at all', () => {
    expect(fmtSpread(0)).toBe('0.00');
  });
});

describe('export', () => {
  const row: SpreadRow = {
    d: '2026-09-03',
    spread: 2.5,
    iv: 12.5,
    hv: 10,
    close: 24_000,
    future: 24_050
  };

  it('writes one row per session, blanking what was never computed', () => {
    expect(ivHvCsv([row, { ...row, d: '2026-09-04', spread: null, iv: null, future: null }])).toBe(
      [
        'date,spread,iv,hv,close,future',
        '2026-09-03,2.5,12.5,10,24000,24050',
        '2026-09-04,,,10,24000,'
      ].join('\n')
    );
  });

  it('names the download after the session it ends on', () => {
    expect(csvFilename('NIFTY', [row])).toBe('iv-hv-NIFTY-2026-09-03.csv');
    expect(csvFilename('NIFTY', [])).toBe('iv-hv-NIFTY.csv');
  });
});
