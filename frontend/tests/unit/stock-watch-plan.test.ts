import { describe, expect, it } from 'vitest';
import {
  type CostRates,
  type PlanInput,
  NO_COSTS,
  compare,
  costsConfigured,
  plan,
  scenario,
  validate
} from '../../app/routes/terminal/future-lab/stock-watch/calc/plan';
import {
  atr,
  gapOf,
  istDay,
  pivots,
  structureOf,
  swings
} from '../../app/routes/terminal/future-lab/stock-watch/calc/levels';
import {
  feedState,
  fmtIndian,
  fmtPercent,
  fmtPrice,
  wire
} from '../../app/routes/terminal/future-lab/stock-watch/calc/format';
import {
  type AlertRule,
  ALERT_COOLDOWN_MS,
  evaluateAlerts
} from '../../app/routes/terminal/future-lab/stock-watch/store';
import type { Candle } from '../../app/lib/shared/charts/tv/LwChart';

/**
 * Risk sizing, scenarios, levels, freshness and alerts.
 *
 * These are the calculations a reader acts on with money, so the tests lean on
 * the cases where being quietly wrong costs something: a stop on the wrong
 * side of entry, a lot size assumed rather than read, a stale quote rendered
 * as current, an alert that fires on every poll until it is switched off.
 */
const BASE: PlanInput = {
  type: 'CE',
  strike: 2500,
  expiry: '2026-10-30',
  lotSize: 250,
  lots: 2,
  entryPremium: 50,
  stopPremium: 30,
  targetPremium: 90,
  capital: 500_000,
  riskPercent: 2
};

describe('trade plan', () => {
  it('sizes risk and reward off the contract’s own lot size', () => {
    const result = plan(BASE);

    expect(result.valid).toBe(true);
    expect(result.riskPerUnit).toBe(20);
    expect(result.riskPerLot).toBe(5_000); // 20 × 250
    expect(result.plannedRisk).toBe(10_000); // × 2 lots
    expect(result.rewardPerLot).toBe(10_000); // 40 × 250
    expect(result.plannedReward).toBe(20_000);
  });

  it('caps lots at what the risk budget actually permits', () => {
    // 2% of ₹5,00,000 is ₹10,000; ₹5,000 of risk a lot allows two.
    const result = plan(BASE);

    expect(result.riskBudget).toBe(10_000);
    expect(result.maxLots).toBe(2);
    expect(plan({ ...BASE, riskPercent: 0.5 }).maxLots).toBe(0);
  });

  it('rejects a stop above entry on a long option, with a reason', () => {
    // Not an exotic configuration to model — arithmetic that would produce a
    // negative risk and an inverted reward-to-risk ratio.
    const result = plan({ ...BASE, stopPremium: 60 });

    expect(result.valid).toBe(false);
    expect(result.issues.some((issue) => /stop must be below entry/.test(issue.message))).toBe(
      true
    );
  });

  it('rejects a target below entry on a long option', () => {
    expect(plan({ ...BASE, targetPremium: 40 }).valid).toBe(false);
  });

  it('refuses to size anything without a lot size', () => {
    // Indian F&O lot sizes differ per underlying and move by circular. A
    // planner that defaulted one would mis-size every trade silently.
    const result = plan({ ...BASE, lotSize: 0 });

    expect(result.valid).toBe(false);
    expect(result.issues.some((issue) => issue.field === 'lotSize')).toBe(true);
  });

  it('warns about an oversized single bet without blocking it', () => {
    const result = plan({ ...BASE, riskPercent: 20 });

    expect(result.valid).toBe(true);
    expect(result.issues.some((issue) => issue.severity === 'warning')).toBe(true);
  });

  it('marks costs excluded rather than reporting them as zero', () => {
    const result = plan(BASE);

    expect(result.costsExcluded).toBe(true);
    expect(costsConfigured(NO_COSTS)).toBe(false);
  });

  it('applies configured charges and counts slippage on both fills', () => {
    const costs: CostRates = {
      brokeragePerOrder: 20,
      sttPercentOnSell: 0.0625,
      exchangePercent: 0.0495,
      sebiPercent: 0.0001,
      stampPercentOnBuy: 0.003,
      gstPercent: 18,
      slippagePerUnit: 0.5
    };
    const result = plan({ ...BASE, costs });

    expect(result.costsExcluded).toBe(false);
    // 500 units × ₹0.50 × two fills is ₹500 of slippage alone.
    expect(result.estimatedCosts).toBeGreaterThan(500);
    expect(result.netAtTarget).toBeLessThan(result.plannedReward);
    expect(result.netAtStop).toBeLessThan(-result.plannedRisk);
  });

  it('reports the daily budget left after this trade’s planned loss', () => {
    const result = plan({ ...BASE, maxDailyLoss: 15_000, lossSoFarToday: 8_000 });

    expect(result.remainingDailyRisk).toBe(-3_000);
  });

  it('breaks even at the strike plus the premium', () => {
    expect(plan(BASE).breakevenLevel).toBe(2550);
    expect(plan({ ...BASE, type: 'PE' }).breakevenLevel).toBe(2450);
  });

  it('validates independently of the full calculation', () => {
    expect(validate({ ...BASE, lots: 0 }).some((issue) => issue.field === 'lots')).toBe(true);
  });
});

describe('scenarios', () => {
  const input = {
    type: 'CE' as const,
    strike: 2500,
    spot: 2500,
    iv: 25,
    days: 30,
    entryPremium: 70,
    lotSize: 250,
    lots: 2
  };

  it('reprices a rally into a profit and a sell-off into a loss', () => {
    const up = scenario(input, { spotMovePercent: 5, ivChange: 0, daysElapsed: 0 });
    const down = scenario(input, { spotMovePercent: -5, ivChange: 0, daysElapsed: 0 });

    expect(up.premium).toBeGreaterThan(down.premium);
    expect(up.pnlPosition).toBeGreaterThan(0);
    expect(down.pnlPosition).toBeLessThan(0);
  });

  it('shows a volatility crush hurting a long option that was right', () => {
    // The most common way a correct directional call still loses money, so it
    // gets a test rather than only a sentence in the UI.
    const flat = scenario(input, { spotMovePercent: 1, ivChange: 0, daysElapsed: 0 });
    const crushed = scenario(input, { spotMovePercent: 1, ivChange: -10, daysElapsed: 0 });

    expect(crushed.premium).toBeLessThan(flat.premium);
  });

  it('uses the payoff at expiry rather than a model stub', () => {
    const expired = scenario(input, { spotMovePercent: 4, ivChange: 0, daysElapsed: 30 });

    expect(expired.atExpiry).toBe(true);
    expect(expired.daysLeft).toBe(0);
    expect(expired.premium).toBeCloseTo(100, 6); // 2600 − 2500
    expect(expired.delta).toBe(0);
  });

  it('is worthless at expiry out of the money', () => {
    const expired = scenario(input, { spotMovePercent: -4, ivChange: 0, daysElapsed: 30 });

    expect(expired.premium).toBe(0);
    expect(expired.pnlPerUnit).toBe(-70);
  });

  it('never leaves time left negative when more days elapse than remain', () => {
    expect(scenario(input, { spotMovePercent: 0, ivChange: 0, daysElapsed: 99 }).daysLeft).toBe(0);
  });
});

describe('contract comparison', () => {
  it('derives per-lot cost, spread and breakeven without ranking', () => {
    const [cheap, rich] = compare([
      {
        strike: 2600,
        type: 'CE',
        expiry: '2026-10-30',
        ltp: 20,
        bid: 19,
        ask: 21,
        volume: 100,
        oi: 500,
        lotSize: 250,
        theta: -2
      },
      {
        strike: 2500,
        type: 'CE',
        expiry: '2026-10-30',
        ltp: 70,
        bid: 69.5,
        ask: 70.5,
        volume: 9000,
        oi: 50_000,
        lotSize: 250,
        theta: -3
      }
    ]);

    expect(cheap?.premiumPerLot).toBe(5_000);
    expect(rich?.premiumPerLot).toBe(17_500);
    expect(cheap?.spreadPercent).toBeCloseTo(10, 6);
    expect(rich?.spreadPercent).toBeCloseTo(1.43, 1);
    expect(cheap?.breakevenLevel).toBe(2620);
    // The cheap wing bleeds a far larger share of its premium per day, which
    // is the comparison the premium column alone hides.
    expect(cheap!.thetaPercentPerDay!).toBeGreaterThan(rich!.thetaPercentPerDay!);
  });

  it('leaves spread undefined when the book is one-sided', () => {
    const [row] = compare([
      {
        strike: 2600,
        type: 'CE',
        expiry: '2026-10-30',
        ltp: 20,
        volume: 100,
        oi: 500,
        lotSize: 250
      }
    ]);

    expect(row?.spread).toBeUndefined();
    expect(row?.spreadPercent).toBeUndefined();
  });
});

// -- levels -------------------------------------------------------------------

/** 09:15 IST on 2026-10-16 is 03:45Z. */
const SESSION_START = Date.UTC(2026, 9, 16, 3, 45) / 1000;

/** A series whose bar extremes follow `pivots`, so swings are where intended. */
function zigzag(pivotPrices: number[]): Candle[] {
  return pivotPrices.map((price, i) => ({
    time: SESSION_START + i * 300,
    open: price,
    high: price + 0.5,
    low: price - 0.5,
    close: price
  }));
}

function bars(count: number, start: number, step = 300): Candle[] {
  return Array.from({ length: count }, (_, i) => ({
    time: start + i * step,
    open: 100 + i,
    high: 101 + i,
    low: 99 + i,
    close: 100.5 + i
  }));
}

describe('levels', () => {
  it('groups bars into IST sessions', () => {
    expect(istDay(SESSION_START)).toBe('2026-10-16');
  });

  it('declines to average an ATR from too few bars', () => {
    expect(atr(bars(10, SESSION_START))).toBeUndefined();
    expect(atr(bars(40, SESSION_START))).toBeGreaterThan(0);
  });

  it('finds a swing high only where the bar beats both sides', () => {
    const series: Candle[] = [
      { time: 1, open: 10, high: 11, low: 9, close: 10 },
      { time: 2, open: 10, high: 12, low: 9, close: 11 },
      { time: 3, open: 11, high: 20, low: 10, close: 19 },
      { time: 4, open: 19, high: 15, low: 8, close: 10 },
      { time: 5, open: 10, high: 14, low: 7, close: 9 }
    ];
    const { highs } = swings(series, 2);

    expect(highs.map((point) => point.price)).toEqual([20]);
  });

  it('refuses to read structure from too few swings', () => {
    const read = structureOf(bars(5, SESSION_START));

    expect(read.state).toBe('unclear');
    expect(read.rule).toMatch(/not enough structure/i);
  });

  it('reads higher highs and higher lows as an uptrend, and names the rule', () => {
    // A zig-zag, not a ramp: a strictly monotonic series has no *local*
    // extremes, so it correctly has no swings and no readable structure.
    // That is the fractal definition doing its job, not a gap in it.
    const read = structureOf(zigzag([10, 6, 12, 8, 14, 10, 16]), 1);

    expect(read.state).toBe('uptrend');
    expect(read.rule).toMatch(/both rising/);
  });

  it('reads lower highs and lower lows as a downtrend', () => {
    const read = structureOf(zigzag([16, 10, 14, 8, 12, 6, 10]), 1);

    expect(read.state).toBe('downtrend');
  });

  it('calls a series with conflicting swings a range', () => {
    const read = structureOf(zigzag([10, 6, 14, 4, 12, 8, 13]), 1);

    expect(read.state).toBe('range');
  });

  it('reads a gap and whether it has filled', () => {
    const up = gapOf(100, { open: 105, high: 108, low: 103 });
    expect(up.kind).toBe('gap_up');
    expect(up.percent).toBeCloseTo(5, 6);
    expect(up.filled).toBe(false);

    expect(gapOf(100, { open: 105, high: 108, low: 99 }).filled).toBe(true);
    expect(gapOf(100, { open: 95, high: 101, low: 92 }).kind).toBe('gap_down');
  });

  it('computes classic floor pivots', () => {
    const levels = pivots({ high: 110, low: 90, close: 100 });

    expect(levels.pivot).toBeCloseTo(100, 6);
    expect(levels.r1).toBeCloseTo(110, 6);
    expect(levels.s1).toBeCloseTo(90, 6);
  });
});

// -- freshness and formatting -------------------------------------------------

describe('feed state', () => {
  it('calls a simulated quote simulated however fresh it is', () => {
    const state = feedState('mock', 1, true);

    expect(state.freshness).toBe('simulated');
    expect(state.message).toMatch(/Not tradeable/);
  });

  it('calls a quote stale only while the market is open', () => {
    expect(feedState('live', 200, true).freshness).toBe('stale');
    // At 20:00 a four-hour-old last print is the close, not a broken feed.
    expect(feedState('live', 14_400, false).freshness).toBe('fresh');
  });

  it('escalates a feed that has clearly stopped', () => {
    const state = feedState('live', 600, true);

    expect(state.freshness).toBe('very_stale');
    expect(state.message).toMatch(/Do not size a trade/);
  });

  it('distinguishes no data from stale data', () => {
    expect(feedState('unavailable', 0, true).freshness).toBe('unavailable');
  });
});

describe('formatting', () => {
  it('renders absent values as a dash, never as zero', () => {
    expect(fmtPrice(undefined)).toBe('—');
    expect(fmtPercent(null)).toBe('—');
    expect(fmtIndian(undefined)).toBe('—');
    expect(fmtPrice(0)).toBe('0.00');
  });

  it('uses Indian units for open interest', () => {
    expect(fmtIndian(1_250_000)).toBe('12.50L');
    expect(fmtIndian(35_000_000)).toBe('3.50Cr');
    expect(fmtIndian(-45_000)).toBe('−45.0K');
  });

  it('signs a percentage with a true minus sign', () => {
    expect(fmtPercent(-1.234)).toBe('−1.23%');
    expect(fmtPercent(1.234)).toBe('+1.23%');
  });

  it('parses a decimal-as-string wire field', () => {
    expect(wire('24.50')).toBe(24.5);
    expect(wire(null)).toBeUndefined();
    expect(wire('')).toBeUndefined();
    expect(wire('nonsense')).toBeUndefined();
  });
});

// -- alerts -------------------------------------------------------------------

describe('alerts', () => {
  const rule = (overrides: Partial<AlertRule> = {}): AlertRule => ({
    id: 'r1',
    symbol: 'RELIANCE',
    kind: 'price_above',
    threshold: 2500,
    enabled: true,
    ...overrides
  });

  it('fires when the observed value crosses the threshold', () => {
    const fired = evaluateAlerts([rule()], { symbol: 'RELIANCE', price: 2510 }, 1_000);

    expect(fired).toHaveLength(1);
    expect(fired[0]?.observed).toBe(2510);
  });

  it('does not fire on another symbol, or when switched off', () => {
    expect(evaluateAlerts([rule()], { symbol: 'TCS', price: 2510 }, 1_000)).toHaveLength(0);
    expect(
      evaluateAlerts([rule({ enabled: false })], { symbol: 'RELIANCE', price: 2510 }, 1_000)
    ).toHaveLength(0);
  });

  it('stays quiet through the cooldown', () => {
    // Without this a price alert on a level the stock is sitting on fires every
    // fifteen seconds until the reader turns alerts off entirely.
    const recent = rule({ lastFiredAt: 1_000 });

    expect(evaluateAlerts([recent], { symbol: 'RELIANCE', price: 2510 }, 2_000)).toHaveLength(0);
    expect(
      evaluateAlerts([recent], { symbol: 'RELIANCE', price: 2510 }, 1_000 + ALERT_COOLDOWN_MS + 1)
    ).toHaveLength(1);
  });

  it('does not fire on a value the page could not measure', () => {
    expect(
      evaluateAlerts([rule({ kind: 'iv_above', threshold: 30 })], { symbol: 'RELIANCE' }, 1_000)
    ).toHaveLength(0);
  });

  it('fires the stale-feed rule only when the feed is actually stale', () => {
    const stale = rule({ kind: 'feed_stale', threshold: 0 });

    expect(evaluateAlerts([stale], { symbol: 'RELIANCE', feedStale: false }, 1_000)).toHaveLength(
      0
    );
    expect(evaluateAlerts([stale], { symbol: 'RELIANCE', feedStale: true }, 1_000)).toHaveLength(1);
  });
});
