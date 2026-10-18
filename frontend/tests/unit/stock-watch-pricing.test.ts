import { describe, expect, it } from 'vitest';
import {
  breakeven,
  extrinsicOf,
  greeks,
  impliedVol,
  intrinsicOf,
  price,
  volFromPercent,
  yearsFromDays
} from '../../app/routes/terminal/future-lab/stock-watch/calc/black-scholes';

/**
 * The option-pricing core the Stock Watch terminal's model figures come from.
 *
 * Checked against closed-form identities rather than against a table of
 * numbers copied from somewhere: put-call parity and the bounds on delta hold
 * for *any* correct Black-Scholes, so a test built on them survives a change
 * of convention that a golden-value test would simply fail.
 *
 * The degenerate cases get as much attention as the ordinary ones, because
 * they are not edge cases on a live chain — at 15:29 on expiry day the entire
 * board is at zero time, and every wing is at zero volatility all day.
 */
const LEG = { type: 'CE' as const, spot: 2500, strike: 2500, years: 30 / 365, vol: 0.25 };

describe('black-scholes price', () => {
  it('satisfies put-call parity', () => {
    // C − P = S − K·e^(−rT). True for any correct pair, whatever the inputs.
    const call = price(LEG);
    const put = price({ ...LEG, type: 'PE' });
    const expected = LEG.spot - LEG.strike * Math.exp(-0.07 * LEG.years);

    expect(call - put).toBeCloseTo(expected, 6);
  });

  it('returns intrinsic value at expiry rather than a model stub', () => {
    // The failure this prevents: a few paise of optimism on a contract that is
    // worthless, read on expiry afternoon as "it still has something left".
    expect(price({ ...LEG, spot: 2600, years: 0 })).toBe(100);
    expect(price({ ...LEG, type: 'PE', spot: 2400, years: 0 })).toBe(100);
    expect(price({ ...LEG, spot: 2400, years: 0 })).toBe(0);
  });

  it('returns intrinsic value when there is no volatility to price with', () => {
    expect(price({ ...LEG, spot: 2600, vol: 0 })).toBe(100);
  });

  it('is worth more with more time, and more with more volatility', () => {
    expect(price({ ...LEG, years: 60 / 365 })).toBeGreaterThan(price(LEG));
    expect(price({ ...LEG, vol: 0.4 })).toBeGreaterThan(price(LEG));
  });

  it('never returns NaN for a degenerate input', () => {
    for (const leg of [
      { ...LEG, spot: 0 },
      { ...LEG, strike: 0 },
      { ...LEG, years: -1 },
      { ...LEG, vol: -0.5 }
    ]) {
      expect(Number.isFinite(price(leg))).toBe(true);
    }
  });
});

describe('greeks', () => {
  it('bounds delta and signs it by side', () => {
    const call = greeks(LEG);
    const put = greeks({ ...LEG, type: 'PE' });

    expect(call.delta).toBeGreaterThan(0);
    expect(call.delta).toBeLessThanOrEqual(1);
    expect(put.delta).toBeLessThan(0);
    expect(put.delta).toBeGreaterThanOrEqual(-1);
    // Another parity identity: δC − δP = 1 for a non-dividend European pair.
    expect(call.delta - put.delta).toBeCloseTo(1, 6);
  });

  it('shares gamma and vega between the two sides', () => {
    const call = greeks(LEG);
    const put = greeks({ ...LEG, type: 'PE' });

    expect(call.gamma).toBeCloseTo(put.gamma, 10);
    expect(call.vega).toBeCloseTo(put.vega, 10);
  });

  it('quotes theta per calendar day and negative for a long option', () => {
    const { theta } = greeks(LEG);

    expect(theta).toBeLessThan(0);
    // The number a broker screen shows for a ₹2,500 ATM option a month out is
    // single-to-low-double-digit rupees a day, not the four-figure annual one.
    expect(Math.abs(theta)).toBeLessThan(100);
  });

  it('quotes vega per volatility point', () => {
    const { vega } = greeks(LEG);
    const bumped = price({ ...LEG, vol: LEG.vol + 0.01 });

    // A one-point IV move should change the premium by roughly vega.
    expect(bumped - price(LEG)).toBeCloseTo(vega, 1);
  });

  it('is all zeros at expiry rather than exploding', () => {
    expect(greeks({ ...LEG, years: 0 })).toEqual({ delta: 0, gamma: 0, theta: 0, vega: 0 });
  });
});

describe('implied volatility', () => {
  it('recovers the volatility a premium was priced from', () => {
    const premium = price(LEG);
    const solved = impliedVol({ type: 'CE', spot: 2500, strike: 2500, years: LEG.years }, premium);

    expect(solved).toBeDefined();
    expect(solved!).toBeCloseTo(LEG.vol, 4);
  });

  it('works on a deep wing, where a Newton step would diverge', () => {
    const wing = { ...LEG, strike: 3200, vol: 0.45 };
    const solved = impliedVol(
      { type: 'CE', spot: wing.spot, strike: wing.strike, years: wing.years },
      price(wing)
    );

    expect(solved!).toBeCloseTo(wing.vol, 3);
  });

  it('declines rather than guessing when the premium is below intrinsic', () => {
    // No volatility reprices a call to less than S−K. Returning the bracket
    // edge would publish a nonsense IV as if it meant something.
    const solved = impliedVol({ type: 'CE', spot: 2600, strike: 2500, years: LEG.years }, 50);

    expect(solved).toBeUndefined();
  });

  it('declines on expiry day and on a zero premium', () => {
    expect(impliedVol({ type: 'CE', spot: 2500, strike: 2500, years: 0 }, 10)).toBeUndefined();
    expect(impliedVol({ type: 'CE', spot: 2500, strike: 2500, years: 0.1 }, 0)).toBeUndefined();
  });
});

describe('value decomposition', () => {
  it('splits a premium into intrinsic and time value', () => {
    expect(intrinsicOf('CE', 2600, 2500)).toBe(100);
    expect(intrinsicOf('CE', 2400, 2500)).toBe(0);
    expect(intrinsicOf('PE', 2400, 2500)).toBe(100);
    expect(extrinsicOf(130, 100)).toBe(30);
  });

  it('floors time value at zero rather than reporting a negative one', () => {
    // A leg trading under intrinsic is a stale print or an arbitrage. Negative
    // "time value" reads as neither and would propagate into the planner.
    expect(extrinsicOf(95, 100)).toBe(0);
  });

  it('breaks even at the strike plus the premium paid', () => {
    expect(breakeven('CE', 2500, 40)).toBe(2540);
    expect(breakeven('PE', 2500, 40)).toBe(2460);
  });
});

describe('unit conversions', () => {
  it('reads a chain IV of 13.2 as 0.132', () => {
    expect(volFromPercent(13.2)).toBeCloseTo(0.132, 10);
  });

  it('treats a missing or non-positive IV as no volatility at all', () => {
    expect(volFromPercent(undefined)).toBe(0);
    expect(volFromPercent(null)).toBe(0);
    expect(volFromPercent(0)).toBe(0);
    expect(volFromPercent(-5)).toBe(0);
  });

  it('converts calendar days to a year fraction, floored at zero', () => {
    expect(yearsFromDays(365)).toBe(1);
    expect(yearsFromDays(-10)).toBe(0);
  });
});
