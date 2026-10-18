/**
 * Open-interest, volatility and futures analytics over an enriched chain.
 *
 * Everything here is descriptive. The ratios and concentrations are facts
 * about the book; the *zones* derived from them are labelled as potential and
 * carry their evidence, because open interest cannot tell you who is on which
 * side of a contract or why. A 10-lakh call-OI strike is as consistent with
 * covered-call writing by a long holder as with a bearish bet, and a terminal
 * that prints "RESISTANCE" over it has made a claim the data cannot support.
 */

import type { ChainRow, EnrichedChain, Leg } from './chain';
import { type OptionType, impliedVol, volFromPercent, yearsFromDays } from './black-scholes';

// -- ratios -------------------------------------------------------------------

/**
 * Put/call ratio. `undefined` — never 0 — when the denominator is empty.
 *
 * Zero is a reading ("no puts at all"), and an empty call side is the absence
 * of one. The distinction matters on a far-month chain where one side has not
 * started trading.
 */
export function ratio(puts: number, calls: number): number | undefined {
  if (!(calls > 0)) return undefined;
  return puts / calls;
}

export interface ChainTotals {
  callOi: number;
  putOi: number;
  callOiChange: number;
  putOiChange: number;
  callVolume: number;
  putVolume: number;
  pcrOi?: number | undefined;
  pcrVolume?: number | undefined;
}

export function totals(rows: ChainRow[]): ChainTotals {
  let callOi = 0;
  let putOi = 0;
  let callOiChange = 0;
  let putOiChange = 0;
  let callVolume = 0;
  let putVolume = 0;

  for (const row of rows) {
    if (row.ce) {
      callOi += row.ce.oi;
      callOiChange += row.ce.oiChange;
      callVolume += row.ce.volume;
    }
    if (row.pe) {
      putOi += row.pe.oi;
      putOiChange += row.pe.oiChange;
      putVolume += row.pe.volume;
    }
  }

  return {
    callOi,
    putOi,
    callOiChange,
    putOiChange,
    callVolume,
    putVolume,
    pcrOi: ratio(putOi, callOi),
    pcrVolume: ratio(putVolume, callVolume)
  };
}

// -- concentration ------------------------------------------------------------

export interface StrikeStat {
  strike: number;
  type: OptionType;
  oi: number;
  oiChange: number;
  oiChangePercent?: number | undefined;
  volume: number;
  ltp: number;
  iv?: number | undefined;
  /** Share of that side's total open interest sitting at this strike. */
  share: number;
}

function statOf(strike: number, leg: Leg, sideTotal: number): StrikeStat {
  return {
    strike,
    type: leg.type,
    oi: leg.oi,
    oiChange: leg.oiChange,
    oiChangePercent: leg.oiChangePercent,
    volume: leg.volume,
    ltp: leg.ltp,
    iv: leg.iv,
    share: sideTotal > 0 ? (leg.oi / sideTotal) * 100 : 0
  };
}

/** Every quoted leg of one side, as flat stats. */
export function sideStats(rows: ChainRow[], type: OptionType): StrikeStat[] {
  const total = rows.reduce(
    (sum, row) => sum + (type === 'CE' ? (row.ce?.oi ?? 0) : (row.pe?.oi ?? 0)),
    0
  );
  const stats: StrikeStat[] = [];
  for (const row of rows) {
    const leg = type === 'CE' ? row.ce : row.pe;
    if (leg) stats.push(statOf(row.strike, leg, total));
  }
  return stats;
}

/** The `n` strikes with the most open interest on one side, biggest first. */
export function topOi(stats: StrikeStat[], n = 5): StrikeStat[] {
  return [...stats].sort((a, b) => b.oi - a.oi).slice(0, n);
}

/** Biggest *additions* to open interest. Positive changes only. */
export function topAdditions(stats: StrikeStat[], n = 5): StrikeStat[] {
  return [...stats]
    .filter((s) => s.oiChange > 0)
    .sort((a, b) => b.oiChange - a.oiChange)
    .slice(0, n);
}

/** Biggest *reductions*. Returned most-negative first. */
export function topReductions(stats: StrikeStat[], n = 5): StrikeStat[] {
  return [...stats]
    .filter((s) => s.oiChange < 0)
    .sort((a, b) => a.oiChange - b.oiChange)
    .slice(0, n);
}

export interface OiZone {
  strike: number;
  kind: 'potential_resistance' | 'potential_support';
  oi: number;
  share: number;
  /** Why this strike was picked out, for the tooltip. */
  basis: string;
}

/**
 * Strikes where open interest is concentrated, named as *potential* zones.
 *
 * Concentration above `minShare` of a side's total is the only rule. Call
 * concentration above spot is flagged as potential resistance and put
 * concentration below it as potential support, because those are the positions
 * whose writers have an incentive to defend the level — an incentive, not a
 * barrier, and not evidence that anyone intends to.
 */
export function oiZones(
  rows: ChainRow[],
  spot: number,
  { minShare = 8, limit = 3 } = {}
): OiZone[] {
  const calls = sideStats(rows, 'CE').filter((s) => s.strike >= spot && s.share >= minShare);
  const puts = sideStats(rows, 'PE').filter((s) => s.strike <= spot && s.share >= minShare);

  const zones: OiZone[] = [
    ...topOi(calls, limit).map((s): OiZone => ({
      strike: s.strike,
      kind: 'potential_resistance',
      oi: s.oi,
      share: s.share,
      basis: `${s.share.toFixed(1)}% of call open interest, above spot.`
    })),
    ...topOi(puts, limit).map((s): OiZone => ({
      strike: s.strike,
      kind: 'potential_support',
      oi: s.oi,
      share: s.share,
      basis: `${s.share.toFixed(1)}% of put open interest, below spot.`
    }))
  ];
  return zones.sort((a, b) => b.share - a.share);
}

/**
 * Max pain: the expiry level at which the least premium is owed to holders.
 *
 * Computed over every listed strike against every other, which is O(n²) in the
 * ladder — fine for the ~40 strikes a stock chain carries. `undefined` on an
 * empty ladder rather than 0, which would plot a marker at the axis origin.
 */
export function maxPain(rows: ChainRow[]): number | undefined {
  if (rows.length === 0) return undefined;
  let best: number | undefined;
  let least = Number.POSITIVE_INFINITY;

  for (const settle of rows) {
    let pain = 0;
    for (const row of rows) {
      pain += (row.ce?.oi ?? 0) * Math.max(0, settle.strike - row.strike);
      pain += (row.pe?.oi ?? 0) * Math.max(0, row.strike - settle.strike);
    }
    if (pain < least) {
      least = pain;
      best = settle.strike;
    }
  }
  return best;
}

// -- volatility ---------------------------------------------------------------

export interface SkewPoint {
  strike: number;
  callIv?: number | undefined;
  putIv?: number | undefined;
  /** Put IV − call IV. The number traders mean by "skew" at a strike. */
  skew?: number | undefined;
}

export function ivSmile(rows: ChainRow[]): SkewPoint[] {
  return rows
    .map((row) => {
      const callIv = row.ce?.iv;
      const putIv = row.pe?.iv;
      const point: SkewPoint = { strike: row.strike };
      if (callIv != null) point.callIv = callIv;
      if (putIv != null) point.putIv = putIv;
      if (callIv != null && putIv != null) point.skew = putIv - callIv;
      return point;
    })
    .filter((point) => point.callIv != null || point.putIv != null);
}

/** ATM implied volatility — the mean of the ATM call and put, when both quote. */
export function atmIv(chain: EnrichedChain): number | undefined {
  const index = chain.rows.findIndex((row) => row.atm);
  const row = index >= 0 ? chain.rows[index] : undefined;
  if (!row) return undefined;
  const quotes = [row.ce?.iv, row.pe?.iv].filter((iv): iv is number => iv != null && iv > 0);
  if (quotes.length === 0) return undefined;
  return quotes.reduce((sum, iv) => sum + iv, 0) / quotes.length;
}

/**
 * Back out IV for a leg the feed did not quote one for.
 *
 * Separate from `atmIv` and never written back into `Leg.iv`: a solved
 * volatility is a model output and the chain's own field is a provider
 * statement. The caller decides whether to show it, and labels it.
 */
export function solveIv(leg: Leg, strike: number, spot: number, days: number): number | undefined {
  const vol = impliedVol({ type: leg.type, spot, strike, years: yearsFromDays(days) }, leg.ltp);
  return vol == null ? undefined : vol * 100;
}

/**
 * Annualised close-to-close historical volatility, in percent.
 *
 * `undefined` below `minSamples` returns rather than a figure computed from
 * four bars. The standard deviation of a handful of returns is not a
 * volatility, and showing it beside a live IV invites a comparison that means
 * nothing.
 */
export function historicalVolatility(
  closes: number[],
  { periodsPerYear = 252, minSamples = 20 } = {}
): number | undefined {
  const usable = closes.filter((close) => close > 0);
  if (usable.length < minSamples + 1) return undefined;

  const returns: number[] = [];
  for (let i = 1; i < usable.length; i += 1) {
    const previous = usable[i - 1];
    const current = usable[i];
    if (previous == null || current == null) continue;
    returns.push(Math.log(current / previous));
  }
  if (returns.length < minSamples) return undefined;

  const mean = returns.reduce((sum, r) => sum + r, 0) / returns.length;
  // Sample variance (n−1): these returns are a sample of the process, not the
  // population, and on 20 bars the difference is ~2.5% of the answer.
  const variance = returns.reduce((sum, r) => sum + (r - mean) ** 2, 0) / (returns.length - 1);
  return Math.sqrt(variance * periodsPerYear) * 100;
}

/**
 * Where today's IV ranks among the readings supplied, 0–100.
 *
 * `undefined` below `minObservations`. An IV percentile over five sessions is
 * arithmetic, not a percentile, and this app has no cross-day IV archive for a
 * single stock yet — so for most symbols this correctly returns nothing and
 * the panel says why.
 */
export function ivPercentile(
  history: number[],
  current: number,
  { minObservations = 60 } = {}
): number | undefined {
  const usable = history.filter((iv) => Number.isFinite(iv) && iv > 0);
  if (usable.length < minObservations) return undefined;
  const below = usable.filter((iv) => iv <= current).length;
  return (below / usable.length) * 100;
}

// -- futures ------------------------------------------------------------------

export interface Basis {
  /** Futures price − spot. Positive is a premium, the normal state. */
  points: number;
  percent: number;
  /** `premium` | `discount` | `flat` — flat inside a one-basis-point band. */
  state: 'premium' | 'discount' | 'flat';
}

export function basisOf(futures: number, spot: number): Basis | undefined {
  if (!(spot > 0) || !(futures > 0)) return undefined;
  const points = futures - spot;
  const percent = (points / spot) * 100;
  const state = Math.abs(percent) < 0.01 ? 'flat' : percent > 0 ? 'premium' : 'discount';
  return { points, percent, state };
}

/**
 * Rollover: what share of the near month has already moved to the next.
 *
 * `nextOi / (nearOi + nextOi)`, the figure the exchange and every desk quote.
 * `undefined` without both legs — a one-contract board cannot answer it, and
 * reporting 0% on a missing far month would read as "nobody has rolled".
 */
export function rolloverPercent(nearOi?: number, nextOi?: number): number | undefined {
  if (nearOi == null || nextOi == null) return undefined;
  const total = nearOi + nextOi;
  if (!(total > 0)) return undefined;
  return (nextOi / total) * 100;
}

// -- helpers ------------------------------------------------------------------

/** A per-strike series for the OI bar charts, ATM-centred by the caller. */
export interface OiBar {
  strike: number;
  callOi: number;
  putOi: number;
  callOiChange: number;
  putOiChange: number;
  callVolume: number;
  putVolume: number;
}

export function oiBars(rows: ChainRow[]): OiBar[] {
  return rows.map((row) => ({
    strike: row.strike,
    callOi: row.ce?.oi ?? 0,
    putOi: row.pe?.oi ?? 0,
    callOiChange: row.ce?.oiChange ?? 0,
    putOiChange: row.pe?.oiChange ?? 0,
    callVolume: row.ce?.volume ?? 0,
    putVolume: row.pe?.volume ?? 0
  }));
}

/** Legs whose build-up classification fired, ranked by how much OI moved. */
export function buildupCandidates(rows: ChainRow[], n = 12) {
  const found: { strike: number; leg: Leg }[] = [];
  for (const row of rows) {
    if (row.ce && row.ce.buildup.state !== 'neutral' && row.ce.buildup.state !== 'unknown') {
      found.push({ strike: row.strike, leg: row.ce });
    }
    if (row.pe && row.pe.buildup.state !== 'neutral' && row.pe.buildup.state !== 'unknown') {
      found.push({ strike: row.strike, leg: row.pe });
    }
  }
  return found.sort((a, b) => Math.abs(b.leg.oiChange) - Math.abs(a.leg.oiChange)).slice(0, n);
}

/** True when `vol` is usable as a Black-Scholes input. */
export function hasVol(iv: number | undefined): boolean {
  return volFromPercent(iv) > 0;
}
