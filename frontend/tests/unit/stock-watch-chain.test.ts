import { describe, expect, it } from 'vitest';
import type { OptionChain, OptionQuote } from '../../app/lib/contexts/broker-connections/types';
import {
  basisOf,
  historicalVolatility,
  ivPercentile,
  maxPain,
  oiZones,
  ratio,
  rolloverPercent,
  sideStats,
  topAdditions,
  topOi,
  topReductions,
  totals
} from '../../app/routes/terminal/future-lab/stock-watch/calc/analytics';
import {
  buildupOf,
  daysToExpiry,
  enrichChain,
  liquidityOf,
  moneynessOf,
  windowAround,
  atmIndex
} from '../../app/routes/terminal/future-lab/stock-watch/calc/chain';

/**
 * Chain enrichment and the analytics over it.
 *
 * The single theme running through these: **a figure the feed did not send is
 * not zero.** It is the difference between "nobody is bidding" and "nothing
 * was said", between a bearish PCR of 0.00 and an un-traded call side, and
 * between a confident build-up classification and one the data cannot make.
 * Each of those is pinned below, because each of them renders as a number a
 * trader would act on.
 */
function leg(overrides: Partial<OptionQuote> = {}): OptionQuote {
  return {
    ltp: '100',
    oi: 10_000,
    oi_change: 1_000,
    volume: 5_000,
    iv: '20',
    bid: '99.5',
    ask: '100.5',
    delta: '0.5',
    ...overrides
  };
}

function chainOf(
  strikes: { strike: number; ce?: Partial<OptionQuote> | null; pe?: Partial<OptionQuote> | null }[],
  overrides: Partial<OptionChain> = {}
): OptionChain {
  return {
    instrument: 'RELIANCE',
    expiry: '2026-10-30',
    expiries: ['2026-10-30', '2026-11-27'],
    spot_price: '2500',
    atm_strike: '2500',
    pcr: null,
    lot_size: 250,
    change_percent: '0.5',
    future_price: '2510',
    india_vix: null,
    india_vix_change_percent: null,
    iv_percentile: null,
    total_call_oi: 0,
    total_put_oi: 0,
    strikes: strikes.map((row) => ({
      strike: String(row.strike),
      ce: row.ce === null ? null : leg(row.ce ?? {}),
      pe: row.pe === null ? null : leg(row.pe ?? {})
    })),
    provenance: {
      source: 'live',
      fetched_at: '2026-10-17T05:00:00Z',
      age_seconds: 2,
      is_stale: false
    },
    ...overrides
  } as OptionChain;
}

const NOW = new Date('2026-10-17T05:00:00Z');

describe('enrichChain', () => {
  it('parses strikes ascending and marks the ATM row', () => {
    const chain = enrichChain(chainOf([{ strike: 2600 }, { strike: 2400 }, { strike: 2500 }]), NOW);

    expect(chain.rows.map((row) => row.strike)).toEqual([2400, 2500, 2600]);
    expect(chain.rows.filter((row) => row.atm).map((row) => row.strike)).toEqual([2500]);
  });

  it('keeps a one-sided strike one-sided', () => {
    // Inventing a zero leg here would corrupt PCR, max pain and every total.
    const chain = enrichChain(chainOf([{ strike: 2500, pe: null }]), NOW);

    expect(chain.rows[0]?.ce).toBeDefined();
    expect(chain.rows[0]?.pe).toBeUndefined();
  });

  it('computes greeks from the leg’s own IV and keeps the broker’s delta apart', () => {
    const chain = enrichChain(chainOf([{ strike: 2500, ce: { delta: '0.42' } }]), NOW);
    const call = chain.rows[0]?.ce;

    expect(call?.quotedDelta).toBe(0.42);
    // The model's own delta is near 0.5 at the money — deliberately not 0.42.
    expect(call?.modelGreeks?.delta).toBeGreaterThan(0.45);
    expect(call?.modelGreeks?.delta).not.toBe(0.42);
  });

  it('computes no greeks at all when the chain carries no IV', () => {
    const chain = enrichChain(chainOf([{ strike: 2500, ce: { iv: null }, pe: { iv: null } }]), NOW);

    expect(chain.rows[0]?.ce?.modelGreeks).toBeUndefined();
    expect(chain.greeksUnavailable).toBe(true);
  });

  it('splits each leg into intrinsic and time value', () => {
    const chain = enrichChain(chainOf([{ strike: 2400, ce: { ltp: '120' } }]), NOW);
    const call = chain.rows[0]?.ce;

    expect(call?.moneyness).toBe('ITM');
    expect(call?.intrinsic).toBe(100);
    expect(call?.extrinsic).toBe(20);
    expect(call?.breakeven).toBe(2520);
  });

  it('prefers the provider’s previous OI over a subtraction', () => {
    const chain = enrichChain(
      chainOf([{ strike: 2500, ce: { oi: 12_000, oi_change: 2_000, previous_oi: 8_000 } }]),
      NOW
    );

    // 2000/8000 = 25%, not 2000/10000 = 20% — the subtraction would be wrong
    // for a leg whose open interest was also adjusted outside the day change.
    expect(chain.rows[0]?.ce?.oiChangePercent).toBeCloseTo(25, 6);
  });
});

describe('moneyness', () => {
  it('reads calls and puts against spot', () => {
    expect(moneynessOf('CE', 2400, 2500)).toBe('ITM');
    expect(moneynessOf('CE', 2600, 2500)).toBe('OTM');
    expect(moneynessOf('PE', 2600, 2500)).toBe('ITM');
    expect(moneynessOf('PE', 2400, 2500)).toBe('OTM');
  });

  it('calls the chain’s own ATM strike ATM on both sides', () => {
    expect(moneynessOf('CE', 2500, 2499, 2500)).toBe('ATM');
    expect(moneynessOf('PE', 2500, 2499, 2500)).toBe('ATM');
  });
});

describe('liquidity', () => {
  it('passes a tight, traded book', () => {
    expect(liquidityOf({ bid: 99.5, ask: 100.5, volume: 5000, oi: 10_000 }).grade).toBe('ok');
  });

  it('calls out a spread that is wide relative to the premium', () => {
    // ₹2 wide is nothing on a ₹300 option and ruinous on a ₹4 one — which is
    // why the test is on the percentage, not the absolute.
    const wide = liquidityOf({ bid: 3, ask: 5, volume: 5000, oi: 10_000 });

    expect(wide.grade).toBe('illiquid');
    expect(wide.spreadPercent).toBeCloseTo(50, 6);
  });

  it('treats a missing side as no two-sided quote, not a zero bid', () => {
    const half = liquidityOf({ ask: 100.5, volume: 5000, oi: 10_000 });

    expect(half.grade).toBe('thin');
    expect(half.spread).toBeUndefined();
    expect(half.reasons[0]).toMatch(/did not price one side/);
  });

  it('refuses to grade an empty book as liquid', () => {
    expect(liquidityOf({ bid: 0, ask: 0, volume: 0, oi: 0 }).grade).toBe('illiquid');
  });
});

describe('build-up classification', () => {
  it('reads the four quadrants off premium against open interest', () => {
    expect(buildupOf({ changePercent: 5, oiChangePercent: 10 }).state).toBe('long_buildup');
    expect(buildupOf({ changePercent: -5, oiChangePercent: 10 }).state).toBe('short_buildup');
    expect(buildupOf({ changePercent: 5, oiChangePercent: -10 }).state).toBe('short_covering');
    expect(buildupOf({ changePercent: -5, oiChangePercent: -10 }).state).toBe('long_unwinding');
  });

  it('refuses to read direction into noise', () => {
    const read = buildupOf({ changePercent: 0.1, oiChangePercent: 20 });

    expect(read.state).toBe('neutral');
    expect(read.rule).toMatch(/deadband/);
  });

  it('declines, and says what it lacked, without a per-leg price change', () => {
    // The alternative — inferring the leg's direction from the underlying — is
    // wrong for every leg whose volatility moved against its delta, and
    // presenting that at the same confidence is the failure being prevented.
    const read = buildupOf({ oiChangePercent: 10 });

    expect(read.state).toBe('unknown');
    expect(read.missing).toContain("the leg's own price change");
  });

  it('carries the rule that fired, for the table to show', () => {
    expect(buildupOf({ changePercent: 5, oiChangePercent: 10 }).rule).toMatch(/open interest up/);
  });
});

describe('ratios and totals', () => {
  it('is undefined, never zero, with an empty denominator', () => {
    // 0.00 PCR is a real and very bearish reading. "No calls quoted" is not.
    expect(ratio(100, 0)).toBeUndefined();
    expect(ratio(0, 100)).toBe(0);
  });

  it('sums each side and skips the legs that are not there', () => {
    const chain = enrichChain(
      chainOf([
        { strike: 2400, ce: { oi: 1000 }, pe: { oi: 3000 } },
        { strike: 2500, ce: { oi: 2000 }, pe: null }
      ]),
      NOW
    );
    const sums = totals(chain.rows);

    expect(sums.callOi).toBe(3000);
    expect(sums.putOi).toBe(3000);
    expect(sums.pcrOi).toBeCloseTo(1, 6);
  });
});

describe('concentration', () => {
  const chain = enrichChain(
    chainOf([
      { strike: 2400, ce: { oi: 1_000, oi_change: -500 }, pe: { oi: 9_000, oi_change: 4_000 } },
      { strike: 2500, ce: { oi: 2_000, oi_change: 100 }, pe: { oi: 1_000, oi_change: 50 } },
      { strike: 2600, ce: { oi: 7_000, oi_change: 3_000 }, pe: { oi: 500, oi_change: -200 } }
    ]),
    NOW
  );

  it('ranks by open interest and by what moved', () => {
    const calls = sideStats(chain.rows, 'CE');

    expect(topOi(calls, 1)[0]?.strike).toBe(2600);
    expect(topAdditions(calls, 1)[0]?.strike).toBe(2600);
    expect(topReductions(calls, 1)[0]?.strike).toBe(2400);
  });

  it('names zones as potential, with the share that produced them', () => {
    const zones = oiZones(chain.rows, 2500);
    const resistance = zones.find((zone) => zone.kind === 'potential_resistance');
    const support = zones.find((zone) => zone.kind === 'potential_support');

    expect(resistance?.strike).toBe(2600);
    expect(support?.strike).toBe(2400);
    expect(resistance?.basis).toMatch(/% of call open interest/);
  });

  it('finds the level owing the least to holders', () => {
    expect(maxPain(chain.rows)).toBeGreaterThan(0);
    expect(maxPain([])).toBeUndefined();
  });
});

describe('volatility statistics', () => {
  it('declines to compute realised volatility from too few returns', () => {
    expect(historicalVolatility([100, 101, 102])).toBeUndefined();
  });

  it('computes it once there is enough history', () => {
    const closes = Array.from({ length: 60 }, (_, i) => 100 * Math.exp(0.01 * Math.sin(i)));

    expect(historicalVolatility(closes)).toBeGreaterThan(0);
  });

  it('refuses an IV percentile over a handful of observations', () => {
    // The guard this pins: a "90th percentile" over nine readings is arithmetic
    // wearing a statistic's clothes, and it is what a premium-seller sizes on.
    expect(ivPercentile([10, 12, 14, 16, 18], 17)).toBeUndefined();
    // 1…100, not 0…99: zero is filtered out as not a volatility at all.
    expect(
      ivPercentile(
        Array.from({ length: 100 }, (_, i) => i + 1),
        50
      )
    ).toBeCloseTo(50, 0);
  });
});

describe('futures maths', () => {
  it('reads a premium, a discount and a flat basis', () => {
    expect(basisOf(2510, 2500)?.state).toBe('premium');
    expect(basisOf(2490, 2500)?.state).toBe('discount');
    expect(basisOf(2500.1, 2500)?.state).toBe('flat');
    expect(basisOf(2510, 2500)?.percent).toBeCloseTo(0.4, 6);
  });

  it('declines without both legs', () => {
    expect(basisOf(2510, 0)).toBeUndefined();
  });

  it('computes rollover as the next month’s share of both months', () => {
    expect(rolloverPercent(60, 40)).toBeCloseTo(40, 6);
  });

  it('withholds rollover rather than reporting 0% on a missing far month', () => {
    expect(rolloverPercent(60, undefined)).toBeUndefined();
    expect(rolloverPercent(0, 0)).toBeUndefined();
  });
});

describe('expiry and windowing', () => {
  it('counts calendar days to the expiry bell', () => {
    expect(daysToExpiry('2026-10-30', new Date('2026-10-17T05:00:00Z'))).toBe(13);
  });

  it('floors a passed expiry at zero rather than going negative', () => {
    expect(daysToExpiry('2026-10-01', new Date('2026-10-17T05:00:00Z'))).toBe(0);
  });

  it('centres the ladder on the strike nearest spot', () => {
    const chain = enrichChain(
      chainOf([{ strike: 2400 }, { strike: 2500 }, { strike: 2600 }, { strike: 2700 }]),
      NOW
    );
    const centre = atmIndex(chain.rows, 2560);

    expect(chain.rows[centre]?.strike).toBe(2600);
    expect(windowAround(chain.rows, centre, 1).map((row) => row.strike)).toEqual([
      2500, 2600, 2700
    ]);
    expect(windowAround(chain.rows, centre, 'all')).toHaveLength(4);
  });
});
