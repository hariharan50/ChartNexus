/**
 * Gann Square-of-9 daily levels.
 *
 * The acceptance values come from the reference workbook via
 * `gann_daily_levels.py` at the repo root; that file and this test must agree
 * digit for digit, which is the whole point of pinning them in both places.
 */

import { describe, expect, it } from 'vitest';
import type { Candle } from '../../app/lib/shared/charts/tv/LwChart';
import {
  buildOverlays,
  excelRound,
  gannDailyLevels,
  gannDegrees,
  gannGuard,
  gannLadder,
  GANN_LINE_KEYS,
  type IndicatorId
} from '../../app/routes/terminal/analyse/indicators';

/** 09:15 IST on 2026-10-26, as epoch seconds — a session open to build from. */
const SESSION_1 = Date.UTC(2026, 9, 26, 3, 45) / 1000;
/** The next day's 09:15 IST. */
const SESSION_2 = SESSION_1 + 86400;

/**
 * Intraday candles on a `stepMinutes` grid starting at `start`.
 *
 * `closes[i]` is the close of bar `i`; opens mirror closes because nothing here
 * reads them.
 */
function bars(start: number, stepMinutes: number, closes: number[]): Candle[] {
  return closes.map((close, i) => ({
    time: start + i * stepMinutes * 60,
    open: close,
    high: close + 1,
    low: close - 1,
    close
  }));
}

describe('excelRound', () => {
  it('rounds half away from zero, unlike Math.round', () => {
    expect(excelRound(0.5)).toBe(1);
    expect(excelRound(1.5)).toBe(2);
    expect(excelRound(2.5)).toBe(3); // banker's rounding would say 2
    // The case Math.round gets wrong: it is half-*up*, so −0.5 → −0.
    expect(excelRound(-0.5)).toBe(-1);
    expect(excelRound(-2.5)).toBe(-3);
  });

  it('rounds to an arbitrary increment', () => {
    expect(excelRound(100.07, 0.05)).toBeCloseTo(100.05, 10);
    expect(excelRound(100.075, 0.05)).toBeCloseTo(100.1, 10);
    expect(excelRound(1.004, 0.01)).toBeCloseTo(1.0, 10);
  });

  it('passes non-finite values through as NaN rather than throwing', () => {
    expect(excelRound(Number.NaN)).toBeNaN();
    expect(excelRound(Number.POSITIVE_INFINITY)).toBeNaN();
  });
});

describe('gannLadder — workbook acceptance values', () => {
  it('reproduces the daily ladder for P = 22726.45', () => {
    const l = gannLadder(22726.45)!;
    expect(l.buyAbove).toBe(22810);
    expect(l.buyTarget1).toBe(22894);
    expect(l.buyTarget2).toBe(22978);
    expect(l.sellBelow).toBe(22643);
    expect(l.sellTarget1).toBe(22560);
    expect(l.sellTarget2).toBe(22477);
  });

  it('reproduces the weekly ladder for P = 23150.85', () => {
    const l = gannLadder(23150.85)!;
    expect(l.buyAbove).toBe(23236);
    expect(l.buyTarget1).toBe(23321);
    expect(l.buyTarget2).toBe(23406);
    expect(l.sellBelow).toBe(23067);
    expect(l.sellTarget1).toBe(22983);
    expect(l.sellTarget2).toBe(22899);
  });

  it('puts the stop on the trigger at the default zero buffer', () => {
    const l = gannLadder(22726.45)!;
    expect(l.buySl).toBe(l.buyAbove);
    expect(l.sellSl).toBe(l.sellBelow);
  });

  it('moves each stop away from its trigger once a buffer is set', () => {
    const l = gannLadder(22726.45, { slBuffer: 10 })!;
    expect(l.buySl).toBe(l.buyAbove - 10);
    expect(l.sellSl).toBe(l.sellBelow + 10);
  });
});

describe('gannLadder — invariants', () => {
  /**
   * `up_distance − down_distance` is exactly 2 in real arithmetic, so the steps
   * differ by exactly `2 / divisor`. In floating point it is not exact:
   * `(√P + 1)² − P` loses low bits to cancellation, and at P ≈ 22726 the error
   * reaches ~2e-12 — which is why this is a tolerance, not an equality.
   */
  it.each([500.25, 1234.56, 22726.45, 23150.85, 99999.99])(
    'up_step − down_step === 2 / divisor at P = %s',
    (base) => {
      for (const divisor of [1.8, 3.6, 7.2]) {
        const l = gannLadder(base, { divisor })!;
        expect(l.upStep - l.downStep).toBeCloseTo(2 / divisor, 9);
      }
    }
  );

  it.each([500.25, 22726.45, 99999.99])('boundaries are the ±1 √-unit rotations at P = %s', (p) => {
    const l = gannLadder(p)!;
    expect(l.upperBoundary).toBeCloseTo((Math.sqrt(p) + 1) ** 2, 9);
    expect(l.lowerBoundary).toBeCloseTo((Math.sqrt(p) - 1) ** 2, 9);
    // The simplifications the doc comment claims.
    expect(l.upperBoundary - p).toBeCloseTo(2 * l.root + 1, 9);
    expect(p - l.lowerBoundary).toBeCloseTo(2 * l.root - 1, 9);
  });

  it('blanks rather than throwing on a price it cannot use', () => {
    expect(gannLadder(0)).toBeNull();
    expect(gannLadder(-5)).toBeNull();
    expect(gannLadder(Number.NaN)).toBeNull();
    expect(gannLadder(Number.POSITIVE_INFINITY)).toBeNull();
    expect(gannLadder(100, { divisor: 0 })).toBeNull();
    expect(gannLadder(100, { divisor: -1 })).toBeNull();
  });

  it('reads the divisor out in degrees', () => {
    expect(gannDegrees(3.6)).toBe(50);
    expect(gannDegrees(1.8)).toBe(100);
    expect(gannDegrees(7.2)).toBe(25);
  });

  it('compounds targets off rounded levels only in legacy mode', () => {
    const legacy = gannLadder(22726.45, { legacyTargetSpacing: true })!;
    const clean = gannLadder(22726.45, { legacyTargetSpacing: false })!;
    // Same trigger either way — the modes only diverge further up the ladder.
    expect(clean.buyAbove).toBe(legacy.buyAbove);
    expect(clean.buyTarget1).toBe(22895); // legacy says 22894
    expect(clean.buyTarget2).toBe(22979); // legacy says 22978
    expect(clean.sellTarget2).toBe(22476); // legacy says 22477
  });
});

describe('gannDailyLevels — anchoring', () => {
  it('anchors on the last bar opening before the window closes, not bar N', () => {
    // 5m bars from 09:15: 09:15, 09:20, 09:25 open inside [09:15, 09:30).
    // 09:25 is the last of them, so its close is the anchor.
    const candles = bars(SESSION_1, 5, [100, 200, 22726.45, 300, 400, 500]);
    const out = gannDailyLevels(candles, '5m');
    expect(out.error).toBeNull();
    expect(out.sessions).toHaveLength(1);
    expect(out.sessions[0]!.levels.base).toBe(22726.45);
    expect(out.sessions[0]!.anchorTime).toBe(SESSION_1 + 10 * 60); // 09:25
    expect(out.sessions[0]!.publishTime).toBe(SESSION_1 + 15 * 60); // 09:30
  });

  it('still finds the right anchor when bars are missing from the window', () => {
    // Only 09:15 and 09:25 print — 09:20 never arrives. Counting "bar 3" would
    // reach past the window; anchoring by time still lands on 09:25.
    const candles: Candle[] = [
      ...bars(SESSION_1, 5, [100]),
      ...bars(SESSION_1 + 10 * 60, 5, [22726.45, 300, 400])
    ];
    const out = gannDailyLevels(candles, '5m');
    expect(out.sessions[0]!.levels.base).toBe(22726.45);
    expect(out.sessions[0]!.anchorTime).toBe(SESSION_1 + 10 * 60);
  });

  it('uses the configured session start over a late first print', () => {
    // The feed's first bar is 09:35, well past the real 09:15 open. With a
    // configured start the window [09:15, 09:30) holds no bar at all, so the
    // session is honestly blank rather than anchored on an arbitrary candle.
    const candles = bars(SESSION_1 + 20 * 60, 5, [100, 200, 300, 400]);
    const configured = gannDailyLevels(candles, '5m', {
      sessionStart: { hour: 9, minute: 15 }
    });
    expect(configured.sessions).toHaveLength(0);
    expect(configured.lines.base.every((p) => p.value === null)).toBe(true);

    // Without one, the first bar present defines the window and it anchors.
    const inferred = gannDailyLevels(candles, '5m');
    expect(inferred.sessions).toHaveLength(1);
  });

  it('recomputes at each session and holds levels flat in between', () => {
    const candles = [
      ...bars(SESSION_1, 5, [1, 2, 22726.45, 10, 11, 12]),
      ...bars(SESSION_2, 5, [3, 4, 23150.85, 20, 21, 22])
    ];
    const out = gannDailyLevels(candles, '5m');
    expect(out.sessions).toHaveLength(2);
    expect(out.sessions[0]!.levels.buyAbove).toBe(22810);
    expect(out.sessions[1]!.levels.buyAbove).toBe(23236);

    // Day one: three nulls then the same value three times — frozen, not drifting.
    const buy = out.lines.buyAbove;
    expect(buy.slice(0, 3).map((p) => p.value)).toEqual([null, null, null]);
    expect(buy.slice(3, 6).map((p) => p.value)).toEqual([22810, 22810, 22810]);
    expect(buy.slice(6, 9).map((p) => p.value)).toEqual([null, null, null]);
    expect(buy.slice(9, 12).map((p) => p.value)).toEqual([23236, 23236, 23236]);
  });
});

describe('gannDailyLevels — no look-ahead', () => {
  it('is null on every bar before the opening range closes', () => {
    const candles = bars(SESSION_1, 5, [1, 2, 22726.45, 10, 11, 12]);
    const out = gannDailyLevels(candles, '5m');
    const publish = out.sessions[0]!.publishTime;
    for (const key of GANN_LINE_KEYS) {
      for (const point of out.lines[key]) {
        if (point.time < publish) expect(point.value).toBeNull();
        else expect(point.value).not.toBeNull();
      }
    }
  });

  it('emits an explicit null per bar rather than omitting it', () => {
    // Omitted bars would let a stepped series hold the previous session's level
    // straight across the gap — the forward-fill rule 3 forbids.
    const candles = bars(SESSION_1, 5, [1, 2, 22726.45, 10]);
    const out = gannDailyLevels(candles, '5m');
    for (const key of GANN_LINE_KEYS) {
      expect(out.lines[key]).toHaveLength(candles.length);
      expect(out.lines[key].map((p) => p.time)).toEqual(candles.map((c) => c.time));
    }
  });

  it('never publishes a session whose opening range never closed', () => {
    // Trading stops at 09:25: the window edge is never reached, so there is no
    // bar on which the anchor is known and nothing may be drawn.
    const candles = bars(SESSION_1, 5, [1, 2, 22726.45]);
    const out = gannDailyLevels(candles, '5m');
    expect(out.sessions).toHaveLength(0);
    expect(out.lines.buyAbove.every((p) => p.value === null)).toBe(true);
  });
});

describe('gannDailyLevels — guards', () => {
  it('refuses a bar coarser than the opening range, and says why', () => {
    const candles = bars(SESSION_1, 60, [22726.45, 100, 200]);
    const out = gannDailyLevels(candles, '1h');
    expect(out.error).toContain('1h');
    expect(out.error).toContain('15');
    expect(out.sessions).toHaveLength(0);
    expect(out.lines.buyAbove).toHaveLength(0);
  });

  it('accepts a bar exactly the size of the opening range', () => {
    const candles = bars(SESSION_1, 15, [22726.45, 100, 200]);
    const out = gannDailyLevels(candles, '15m');
    expect(out.error).toBeNull();
    expect(out.sessions[0]!.levels.buyAbove).toBe(22810);
  });

  it('declines when the interval is unknown instead of guessing', () => {
    const out = gannDailyLevels(bars(SESSION_1, 5, [1, 2, 3, 4]), undefined);
    expect(out.error).toContain('interval unknown');
  });

  it('blanks a non-positive anchor without raising', () => {
    const candles = bars(SESSION_1, 5, [1, 2, 0, 10, 11]);
    expect(() => gannDailyLevels(candles, '5m')).not.toThrow();
    const out = gannDailyLevels(candles, '5m');
    expect(out.sessions).toHaveLength(0);
    expect(out.lines.buyAbove.every((p) => p.value === null)).toBe(true);
    expect(out.error).toBeNull(); // blank, not an error banner
  });

  it('warns but still draws when the anchor is low-priced', () => {
    const candles = bars(SESSION_1, 5, [1, 2, 120.5, 10, 11]);
    const out = gannDailyLevels(candles, '5m');
    expect(out.warning).toContain('120.50');
    expect(out.sessions).toHaveLength(1);
    expect(out.lines.buyAbove.at(-1)!.value).not.toBeNull();
  });

  it('is quiet at a normal index price', () => {
    const out = gannDailyLevels(bars(SESSION_1, 5, [1, 2, 22726.45, 10]), '5m');
    expect(out.warning).toBeNull();
  });

  it('handles an empty series', () => {
    const out = gannDailyLevels([], '5m');
    expect(out.error).toBeNull();
    expect(out.sessions).toHaveLength(0);
  });

  it('gannGuard reports exactly what the series did', () => {
    expect(gannGuard(bars(SESSION_1, 60, [1, 2, 3]), '1h').error).toContain('1h');
    expect(gannGuard(bars(SESSION_1, 5, [1, 2, 22726.45, 9]), '5m')).toEqual({
      error: null,
      warning: null
    });
  });
});

describe('buildOverlays — Gann', () => {
  const candles = bars(SESSION_1, 5, [1, 2, 22726.45, 10, 11, 12]);

  it('emits seven stepped, labelled lines on the price pane', () => {
    const overlays = buildOverlays(new Set<IndicatorId>(['gann']), candles, undefined, '5m');
    expect(overlays).toHaveLength(7);
    for (const spec of overlays) {
      expect(spec.paneIndex).toBe(0);
      expect(spec.stepped).toBe(true);
      expect(spec.priceLabel).toBe(true);
    }
    expect(overlays.map((o) => o.id)).toEqual([
      'gann-base',
      'gann-buy',
      'gann-bt1',
      'gann-bt2',
      'gann-sell',
      'gann-st1',
      'gann-st2'
    ]);
  });

  it('draws every rung as the same solid hairline', () => {
    const overlays = buildOverlays(new Set<IndicatorId>(['gann']), candles, undefined, '5m');
    for (const spec of overlays) {
      expect(spec.lineWidth).toBe(1);
      expect(spec.lineStyle).toBe('solid');
      // Full opacity throughout — no half-alpha target rungs.
      expect(spec.color).toMatch(/^#[0-9a-f]{6}$/i);
    }
  });

  it('colours by side, with the anchor its own colour between them', () => {
    const overlays = buildOverlays(new Set<IndicatorId>(['gann']), candles, undefined, '5m');
    const at = (id: string) => overlays.find((o) => o.id === id)!.color;
    const buy = at('gann-buy');
    const sell = at('gann-sell');
    expect(at('gann-bt1')).toBe(buy);
    expect(at('gann-bt2')).toBe(buy);
    expect(at('gann-st1')).toBe(sell);
    expect(at('gann-st2')).toBe(sell);
    // The anchor belongs to neither side, so it shares neither colour.
    expect(at('gann-base')).not.toBe(buy);
    expect(at('gann-base')).not.toBe(sell);
  });

  it('draws nothing at all when the guard trips', () => {
    const hourly = bars(SESSION_1, 60, [22726.45, 100, 200]);
    expect(buildOverlays(new Set<IndicatorId>(['gann']), hourly, undefined, '1h')).toHaveLength(0);
  });

  it('declines when no interval is passed', () => {
    expect(buildOverlays(new Set<IndicatorId>(['gann']), candles, undefined)).toHaveLength(0);
  });

  it('leaves the other indicators untouched', () => {
    const long = bars(
      SESSION_1,
      5,
      Array.from({ length: 60 }, (_, i) => 100 + i)
    );
    const withGann = buildOverlays(new Set<IndicatorId>(['sma20', 'gann']), long, undefined, '5m');
    const without = buildOverlays(new Set<IndicatorId>(['sma20']), long, undefined, '5m');
    expect(withGann.find((o) => o.id === 'sma20')).toEqual(without.find((o) => o.id === 'sma20'));
  });
});
