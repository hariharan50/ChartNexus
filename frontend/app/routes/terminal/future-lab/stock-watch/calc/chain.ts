/**
 * The option chain, enriched into the rows the Stock Watch table renders.
 *
 * Three rules shape every function here, and all three exist because the
 * opposite behaviour produces a screen that is confidently wrong:
 *
 * **Absent is not zero.** A leg the feed did not quote carries `undefined`,
 * never 0. A 0.00 bid reads as "nobody is bidding", which is a tradeable fact;
 * the truth is that nothing was said. Every downstream aggregate — PCR, the
 * spread warning, the build-up read — skips `undefined` and counts 0.
 *
 * **Provider figures and model figures never share a field.** `quotedDelta` is
 * the broker's; `modelGreeks` is this app's Black-Scholes. The table labels
 * which it is showing, because a reader hedging on delta needs to know whether
 * it came off the exchange or out of an assumption about volatility.
 *
 * **A classification is a heuristic with its evidence attached.** `buildup`
 * carries the rule that fired and what was missing, so the UI can show the
 * working rather than an oracle's verdict. Open interest alone cannot
 * distinguish a writer from a hedger from a market maker, and nothing here
 * pretends otherwise.
 */

import type { OptionChain, OptionQuote, StrikeRow } from '$contexts/broker-connections/types';
import {
  type Greeks,
  type OptionType,
  breakeven,
  extrinsicOf,
  greeks,
  intrinsicOf,
  volFromPercent,
  yearsFromDays
} from './black-scholes';

export type Moneyness = 'ITM' | 'ATM' | 'OTM';

/** The four positioning states, plus an honest refusal. */
export type Buildup =
  'long_buildup' | 'short_buildup' | 'short_covering' | 'long_unwinding' | 'neutral' | 'unknown';

export const BUILDUP_LABEL: Record<Buildup, string> = {
  long_buildup: 'Long buildup',
  short_buildup: 'Short buildup',
  short_covering: 'Short covering',
  long_unwinding: 'Long unwinding',
  neutral: 'No clear pattern',
  unknown: 'Not enough data'
};

/**
 * Why a leg is hard to trade, in increasing severity.
 *
 * `ok` is not a promise of a fill. It means nothing on this row crossed a
 * threshold worth interrupting the reader over.
 */
export type LiquidityGrade = 'ok' | 'thin' | 'illiquid';

export interface Liquidity {
  grade: LiquidityGrade;
  /** Ask − bid, in rupees. `undefined` when either side was not quoted. */
  spread?: number | undefined;
  /** The spread as a percentage of the mid. The figure that actually matters:
      ₹2 wide is nothing on a ₹300 option and ruinous on a ₹4 one. */
  spreadPercent?: number | undefined;
  /** Mid-price, when both sides are quoted. */
  mid?: number | undefined;
  /** Plain-language reasons, for a tooltip. Empty when `ok`. */
  reasons: string[];
}

export interface BuildupRead {
  state: Buildup;
  /** The rule that fired, verbatim, so the table can show its working. */
  rule: string;
  /** Inputs the classification wanted and did not get. */
  missing: string[];
}

export interface Leg {
  type: OptionType;
  ltp: number;
  /** The leg's own day move. `undefined` when the feed did not quote it. */
  change?: number | undefined;
  changePercent?: number | undefined;
  oi: number;
  oiChange: number;
  oiChangePercent?: number | undefined;
  previousOi?: number | undefined;
  volume: number;
  /** Implied volatility in percent, as the chain quotes it. */
  iv?: number | undefined;
  bid?: number | undefined;
  ask?: number | undefined;
  bidQty?: number | undefined;
  askQty?: number | undefined;
  /** The broker's delta. Distinct from `modelGreeks.delta` on purpose. */
  quotedDelta?: number | undefined;
  /** Black-Scholes, from this leg's own IV. `undefined` without an IV to use. */
  modelGreeks?: Greeks | undefined;
  moneyness: Moneyness;
  intrinsic: number;
  extrinsic: number;
  /** Underlying level at which a long position breaks even at expiry,
      before costs. */
  breakeven: number;
  liquidity: Liquidity;
  buildup: BuildupRead;
}

export interface ChainRow {
  strike: number;
  atm: boolean;
  ce?: Leg | undefined;
  pe?: Leg | undefined;
}

export interface EnrichedChain {
  rows: ChainRow[];
  spot: number;
  atmStrike?: number | undefined;
  expiry: string;
  expiries: string[];
  lotSize?: number | undefined;
  futurePrice?: number | undefined;
  /** Calendar days to expiry, from the session date. */
  daysToExpiry: number;
  totalCallOi: number;
  totalPutOi: number;
  /** True when the chain carried no IV at all, so no model greeks exist. */
  greeksUnavailable: boolean;
}

/** Below this, a move is rounding rather than direction — on either axis. */
export const BUILDUP_DEADBAND_PERCENT = 0.5;

/** Spread wider than this share of the mid is called out. */
const THIN_SPREAD_PERCENT = 2;
const ILLIQUID_SPREAD_PERCENT = 6;
/** Fewer traded units than this and the spread above is barely a market. */
const THIN_VOLUME = 500;

function num(value: string | null | undefined): number | undefined {
  if (value == null || value === '') return undefined;
  const parsed = Number.parseFloat(value);
  return Number.isFinite(parsed) ? parsed : undefined;
}

/**
 * Calendar days from today to an ISO expiry date, in IST. Never negative.
 *
 * The *difference between two calendar dates*, not a fractional duration
 * rounded. On 17 October with a 30 October expiry every screen in the market
 * says 13 days; ceiling the 13.2-day gap would say 14, and the figure feeds
 * the pricing model as well as the header. Expiry day itself is 0, which
 * correctly collapses the model to the payoff — an expiry-day Black-Scholes
 * value is noise, and the scenario grid handles that row as the payoff anyway.
 */
export function daysToExpiry(expiry: string, from: Date = new Date()): number {
  const target = Date.parse(`${expiry}T00:00:00+05:30`);
  if (!Number.isFinite(target)) return 0;
  // Both ends shifted into IST, then floored to midnight, so the subtraction
  // counts dates rather than hours.
  const istMidnight = (at: number) => Math.floor((at + IST_OFFSET_MS) / 86_400_000) * 86_400_000;
  return Math.max(0, (istMidnight(target) - istMidnight(from.getTime())) / 86_400_000);
}

/** IST is a fixed UTC+5:30; a timestamp is UTC. */
const IST_OFFSET_MS = 5.5 * 60 * 60 * 1000;

/**
 * Moneyness against the strike the chain is centred on.
 *
 * Measured against *spot*, not against the future. The two differ by the basis
 * and a reader checking whether a call is in the money is asking about the
 * share price, which is what settlement uses.
 */
export function moneynessOf(
  type: OptionType,
  strike: number,
  spot: number,
  atm?: number
): Moneyness {
  if (atm != null && strike === atm) return 'ATM';
  if (type === 'CE') return spot > strike ? 'ITM' : 'OTM';
  return spot < strike ? 'ITM' : 'OTM';
}

export function liquidityOf(leg: {
  bid?: number | undefined;
  ask?: number | undefined;
  volume: number;
  oi: number;
}): Liquidity {
  const reasons: string[] = [];
  const { bid, ask, volume, oi } = leg;

  if (bid == null || ask == null) {
    reasons.push('No two-sided quote — the feed did not price one side.');
    return { grade: 'thin', reasons };
  }

  const spread = ask - bid;
  const mid = (ask + bid) / 2;
  // A zero mid is an untraded wing, not a free option. Grading it on a
  // percentage would divide by zero and call it liquid.
  if (!(mid > 0)) {
    return { grade: 'illiquid', spread, mid, reasons: ['No mid price — the book is empty.'] };
  }

  const spreadPercent = (spread / mid) * 100;
  let grade: LiquidityGrade = 'ok';

  if (spreadPercent >= ILLIQUID_SPREAD_PERCENT) {
    grade = 'illiquid';
    reasons.push(`Spread is ${spreadPercent.toFixed(1)}% of mid — entry and exit cost real money.`);
  } else if (spreadPercent >= THIN_SPREAD_PERCENT) {
    grade = 'thin';
    reasons.push(`Spread is ${spreadPercent.toFixed(1)}% of mid.`);
  }

  if (volume < THIN_VOLUME) {
    if (grade === 'ok') grade = 'thin';
    reasons.push(`Only ${volume.toLocaleString('en-IN')} traded today.`);
  }
  if (oi <= 0) {
    grade = 'illiquid';
    reasons.push('No open interest — nothing is positioned here.');
  }

  return { grade, spread, spreadPercent, mid, reasons };
}

/**
 * The 2×2 read of a leg's own premium against its own open interest.
 *
 * The axes are deliberately the *option's* price and the *option's* OI, not
 * the underlying's. Inferring a call's direction from the index is the
 * shortcut the rest of this app takes when it has nothing better, and it is
 * wrong for every leg whose volatility moved against its delta — which on a
 * results day is most of them. When the feed does not quote a per-leg change
 * this returns `unknown` and says what it was missing, rather than falling
 * back to the inference and presenting it at the same confidence.
 */
export function buildupOf(input: {
  changePercent?: number | undefined;
  oiChangePercent?: number | undefined;
  deadband?: number | undefined;
}): BuildupRead {
  const deadband = input.deadband ?? BUILDUP_DEADBAND_PERCENT;
  const missing: string[] = [];
  if (input.changePercent == null) missing.push("the leg's own price change");
  if (input.oiChangePercent == null) missing.push('open-interest change');

  if (input.changePercent == null || input.oiChangePercent == null) {
    return { state: 'unknown', rule: 'Not classified — see missing inputs.', missing };
  }

  const priceMove = input.changePercent;
  const oiMove = input.oiChangePercent;

  if (Math.abs(priceMove) < deadband || Math.abs(oiMove) < deadband) {
    return {
      state: 'neutral',
      rule: `Both moves inside the ±${deadband}% deadband — too small to read as direction.`,
      missing
    };
  }

  const priceUp = priceMove > 0;
  const oiUp = oiMove > 0;
  if (priceUp && oiUp) {
    return {
      state: 'long_buildup',
      rule: 'Premium up and open interest up — money entering on the long side of this leg.',
      missing
    };
  }
  if (!priceUp && oiUp) {
    return {
      state: 'short_buildup',
      rule: 'Premium down and open interest up — money entering on the short side (writing).',
      missing
    };
  }
  if (priceUp && !oiUp) {
    return {
      state: 'short_covering',
      rule: 'Premium up and open interest down — shorts closing out.',
      missing
    };
  }
  return {
    state: 'long_unwinding',
    rule: 'Premium down and open interest down — longs closing out.',
    missing
  };
}

function toLeg(
  quote: OptionQuote | null,
  type: OptionType,
  strike: number,
  ctx: { spot: number; atm?: number | undefined; years: number }
): Leg | undefined {
  if (!quote) return undefined;

  const ltp = num(quote.ltp) ?? 0;
  const iv = num(quote.iv);
  const previousOi = quote.previous_oi ?? undefined;
  // Prefer the provider's own prior open interest; fall back to today's change
  // only when the subtraction has something to subtract from.
  const base = previousOi ?? quote.oi - quote.oi_change;
  const oiChangePercent = base > 0 ? (quote.oi_change / base) * 100 : undefined;

  const intrinsic = intrinsicOf(type, ctx.spot, strike);
  const vol = volFromPercent(iv);
  const modelGreeks =
    vol > 0 && ctx.years > 0
      ? greeks({ type, spot: ctx.spot, strike, years: ctx.years, vol })
      : undefined;

  const bid = num(quote.bid);
  const ask = num(quote.ask);

  const changePercent = num(quote.change_percent ?? null);

  return {
    type,
    ltp,
    change: num(quote.change ?? null),
    changePercent,
    oi: quote.oi,
    oiChange: quote.oi_change,
    oiChangePercent,
    previousOi,
    volume: quote.volume,
    iv,
    bid,
    ask,
    bidQty: quote.bid_qty ?? undefined,
    askQty: quote.ask_qty ?? undefined,
    quotedDelta: num(quote.delta),
    modelGreeks,
    moneyness: moneynessOf(type, strike, ctx.spot, ctx.atm),
    intrinsic,
    extrinsic: extrinsicOf(ltp, intrinsic),
    breakeven: breakeven(type, strike, ltp),
    liquidity: liquidityOf({ bid, ask, volume: quote.volume, oi: quote.oi }),
    buildup: buildupOf({ changePercent, oiChangePercent })
  };
}

/** Parse and enrich a wire chain. Strike-ascending, one row per strike. */
export function enrichChain(chain: OptionChain, now: Date = new Date()): EnrichedChain {
  const spot = num(chain.spot_price) ?? 0;
  const atmStrike = num(chain.atm_strike);
  const days = daysToExpiry(chain.expiry, now);
  const years = yearsFromDays(days);

  const rows: ChainRow[] = chain.strikes
    .map((row: StrikeRow) => {
      const strike = num(row.strike) ?? Number.NaN;
      return {
        strike,
        atm: atmStrike != null && strike === atmStrike,
        ce: toLeg(row.ce, 'CE', strike, { spot, atm: atmStrike, years }),
        pe: toLeg(row.pe, 'PE', strike, { spot, atm: atmStrike, years })
      };
    })
    .filter((row) => Number.isFinite(row.strike))
    .sort((a, b) => a.strike - b.strike);

  const greeksUnavailable = rows.every((row) => !row.ce?.modelGreeks && !row.pe?.modelGreeks);

  return {
    rows,
    spot,
    atmStrike,
    expiry: chain.expiry,
    expiries: [...chain.expiries],
    lotSize: chain.lot_size ?? undefined,
    futurePrice: num(chain.future_price),
    daysToExpiry: days,
    totalCallOi: chain.total_call_oi,
    totalPutOi: chain.total_put_oi,
    greeksUnavailable
  };
}

/** The row index nearest `spot`, or -1 for an empty ladder. */
export function atmIndex(rows: ChainRow[], spot: number, fallback?: number): number {
  if (rows.length === 0) return -1;
  const target = Number.isFinite(spot) && spot > 0 ? spot : fallback;
  if (target == null || !Number.isFinite(target)) return Math.floor(rows.length / 2);

  let best = 0;
  let bestDistance = Number.POSITIVE_INFINITY;
  rows.forEach((row, index) => {
    const distance = Math.abs(row.strike - target);
    if (distance < bestDistance) {
      bestDistance = distance;
      best = index;
    }
  });
  return best;
}

/** `count` strikes either side of the ATM row; `'all'` returns everything. */
export function windowAround(rows: ChainRow[], centre: number, count: number | 'all'): ChainRow[] {
  if (count === 'all' || centre < 0) return rows;
  return rows.slice(Math.max(0, centre - count), Math.min(rows.length, centre + count + 1));
}
