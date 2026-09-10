/**
 * Wire types and pure derivations for the Volatility Skew tool.
 *
 * The backend serves a whole session in one payload — every capture's call and
 * put IV at every strike, plus the open interest on each side — so scrubbing
 * the timeline, windowing the strikes, re-basing the axis on the money and
 * switching what the curve blends are all client-side and instant.
 *
 * The one piece of real judgement here is {@link otmIv}: which of a strike's
 * two volatilities the curve takes. Everything else is projection.
 */

import { apiFetch } from '$shared/api/client';

// Shared session/clock/slider helpers, reused rather than duplicated so this
// page reads the same session the OI-family pages do.
export {
  CALL_COLOR,
  PUT_COLOR,
  OI_INSTRUMENTS,
  REFETCH_MS,
  STALE_AFTER_MS,
  clockLabel,
  dateLabel,
  fmtOi,
  freshnessLabel,
  inferStep,
  priceIndex,
  sessionPositions,
  sessionTicks,
  timeLabel,
  type Instrument,
  type SliderTick
} from '../open-interest/oi-data';

export { expiryLabel } from '../atm-straddle/straddle-data';
export { prevTradingDay } from '../premium-decay/premium-decay-data';

import { inferStep } from '../open-interest/oi-data';

// -- the payload ------------------------------------------------------------

/** One capture's per-strike volatility and open interest. */
export interface SkewFrame {
  t: string;
  spot: number;
  /** `null` on captures taken before the ATM column was denormalised. */
  atm: number | null;
  /**
   * The tradable future at this capture, falling back to spot on rows older
   * than that column. `null` when neither was recorded.
   *
   * Unused by this page — the skew is read across strikes at one instant, not
   * against price — but the IV Intraday page draws volatility against it, and
   * one payload carrying both beats that page issuing a second query for one
   * number per frame.
   */
  future: number | null;
  /** Aligned to {@link SkewView.strikes}; `null` where the leg carried no IV. */
  ce_iv: (number | null)[];
  pe_iv: (number | null)[];
  /** Aligned the same way. `0` where the leg was not quoted — see the service. */
  call_oi: number[];
  put_oi: number[];
}

export interface SkewView {
  instrument_id: string;
  symbol: string;
  expiry_date: string | null;
  lot_size: number | null;
  spot: number;
  atm_strike: number | null;
  open_ts: string;
  now_ts: string;
  data_quality: 'intraday' | 'empty';
  open_is_estimated: boolean;
  /**
   * Fraction of legs that carried a quoted IV, 0–1.
   *
   * Without it a chain nobody priced volatility on draws as an empty curve,
   * indistinguishable from a strike range nobody trades.
   */
  iv_coverage: number;
  strikes: number[];
  t: string[];
  frames: SkewFrame[];
}

export function getSkew(
  instrument: string,
  opts: { date?: string | undefined } = {},
  fetcher?: typeof fetch
): Promise<SkewView> {
  return apiFetch<SkewView>({
    url: `/options-lab/skew/${encodeURIComponent(instrument)}`,
    params: opts.date ? { date: opts.date } : {},
    fetcher
  });
}

// -- the curve --------------------------------------------------------------

/**
 * The out-of-the-money volatility at each strike — what "skew" actually means.
 *
 * Below spot the put is the OTM leg, above it the call. Those are the contracts
 * that carry the risk premium and that anyone buying protection is paying for;
 * the in-the-money leg at the same strike is thinly quoted and its inverted IV
 * is mostly the width of the spread. Taking one side across the whole ladder
 * instead would draw the ITM noise into half the curve.
 *
 * At the money, where neither leg is out of it, the two are averaged when both
 * are quoted — a single-sided pick there would put a step in the middle of the
 * curve at the one strike everyone reads.
 */
export function otmIv(frame: SkewFrame, strikes: number[], spot: number): (number | null)[] {
  return strikes.map((strike, index) => {
    const call = frame.ce_iv[index] ?? null;
    const put = frame.pe_iv[index] ?? null;

    if (strike < spot) return put;
    if (strike > spot) return call;
    // Exactly at the money — vanishingly rare with a real spot, but the ATM
    // strike itself lands here whenever spot sits on a round number.
    if (call === null) return put;
    if (put === null) return call;
    return (call + put) / 2;
  });
}

/**
 * Call IV ÷ put IV at each strike.
 *
 * Above 1 the calls at that strike are bid richer than the puts. `null` unless
 * both sides were quoted and the put IV is non-zero: a ratio with an empty
 * denominator is undefined, and 0 would draw a false floor.
 */
export function volRatio(frame: SkewFrame, strikes: number[]): (number | null)[] {
  return strikes.map((_, index) => {
    const call = frame.ce_iv[index] ?? null;
    const put = frame.pe_iv[index] ?? null;
    if (call === null || put === null || put === 0) return null;
    return call / put;
  });
}

/** One row per strike — everything the chart and its tooltip read. */
export interface SkewBar {
  strike: number;
  label: string;
  iv: number | null;
  callIv: number | null;
  putIv: number | null;
  callOi: number;
  putOi: number;
  ratio: number | null;
}

export type AxisView = 'strike' | 'atm';

/**
 * The rows for one capture, already windowed and labelled.
 *
 * `window` is a pair of indices into `strikes`, inclusive — the strike slider
 * works in index space, like every other slider on these pages.
 */
export function skewBars(
  view: SkewView,
  frame: SkewFrame,
  { window, axis }: { window: [number, number]; axis: AxisView }
): SkewBar[] {
  const [lo, hi] = clampWindow(window, view.strikes.length);
  const iv = otmIv(frame, view.strikes, frame.spot);
  const ratio = volRatio(frame, view.strikes);
  const step = inferStep(view.strikes);
  // Offsets are measured from this capture's own money, so scrubbing keeps the
  // zero under the money rather than under wherever it was at the close.
  const anchor = frame.atm ?? nearestStrike(view.strikes, frame.spot);

  const bars: SkewBar[] = [];
  for (let index = lo; index <= hi; index++) {
    const strike = view.strikes[index];
    if (strike === undefined) continue;
    bars.push({
      strike,
      label: axis === 'atm' ? atmLabel(strike, anchor, step) : String(strike),
      iv: iv[index] ?? null,
      callIv: frame.ce_iv[index] ?? null,
      putIv: frame.pe_iv[index] ?? null,
      callOi: frame.call_oi[index] ?? 0,
      putOi: frame.put_oi[index] ?? 0,
      ratio: ratio[index] ?? null
    });
  }
  return bars;
}

/** `ATM`, `ATM+2`, `ATM-3` — position on the ladder rather than price. */
export function atmLabel(strike: number, atm: number | null, step: number): string {
  if (atm === null || step <= 0) return String(strike);
  const steps = Math.round((strike - atm) / step);
  if (steps === 0) return 'ATM';
  return `ATM${steps > 0 ? '+' : '−'}${Math.abs(steps)}`;
}

/** The strike on the ladder closest to a price. `null` for an empty ladder. */
export function nearestStrike(strikes: number[], price: number): number | null {
  let best: number | null = null;
  let bestGap = Infinity;
  for (const strike of strikes) {
    const gap = Math.abs(strike - price);
    if (gap < bestGap) {
      bestGap = gap;
      best = strike;
    }
  }
  return best;
}

/** Keeps a slider window inside the ladder, and the low handle below the high. */
export function clampWindow([lo, hi]: [number, number], length: number): [number, number] {
  if (length === 0) return [0, 0];
  const last = length - 1;
  const low = Math.min(Math.max(0, Math.round(lo)), last);
  const high = Math.min(Math.max(low, Math.round(hi)), last);
  return [low, high];
}

/**
 * The strike the curve bottoms out at.
 *
 * The trough of the smile is where the market prices the least movement, which
 * is not generally the money — the gap between the two is the skew's whole
 * point. `null` for a curve with nothing quoted on it.
 */
export function lowestIvStrike(bars: SkewBar[]): number | null {
  let best: number | null = null;
  let bestIv = Infinity;
  for (const bar of bars) {
    if (bar.iv === null || bar.iv >= bestIv) continue;
    bestIv = bar.iv;
    best = bar.strike;
  }
  return best;
}

/**
 * A prior session's curve mapped onto today's axis.
 *
 * By strike when the axis is strikes, and by *offset from that day's own money*
 * when it is ATM± — which is the only way the comparison means anything once
 * the index has moved a few hundred points overnight.
 */
export function overlayValues(
  bars: SkewBar[],
  prior: SkewView | undefined,
  axis: AxisView,
  todayAtm: number | null
): (number | null)[] {
  const frame = prior?.frames.at(-1);
  if (!prior || !frame) return bars.map(() => null);

  const iv = otmIv(frame, prior.strikes, frame.spot);
  const priorAtm = frame.atm ?? nearestStrike(prior.strikes, frame.spot);
  const step = inferStep(prior.strikes);
  const shift = axis === 'atm' && priorAtm !== null && todayAtm !== null ? priorAtm - todayAtm : 0;

  return bars.map((bar) => {
    const index = prior.strikes.indexOf(nearestOnStep(bar.strike + shift, step));
    return index < 0 ? null : (iv[index] ?? null);
  });
}

/** Snaps a shifted strike back onto the ladder's own grid. */
function nearestOnStep(value: number, step: number): number {
  return step > 0 ? Math.round(value / step) * step : value;
}

// -- formatting -------------------------------------------------------------

/** A volatility, one decimal. The axis and tooltip both read in points. */
export function fmtIv(value: number): string {
  return value.toFixed(1);
}

/** The coverage warning's text, or `null` when the chain was fully priced. */
export function coverageNote(view: SkewView): string | null {
  if (view.iv_coverage >= 0.999) return null;
  if (view.iv_coverage <= 0) return 'No implied volatility was quoted for this session.';
  return `Implied volatility quoted on ${Math.round(view.iv_coverage * 100)}% of legs — gaps in the curve are unpriced strikes, not flat ones.`;
}

// -- CSV export -------------------------------------------------------------

export function skewCsv(bars: SkewBar[]): string {
  const header = 'strike,iv,call_iv,put_iv,call_oi,put_oi,vol_ratio';
  const body = bars.map((bar) =>
    [
      bar.strike,
      bar.iv ?? '',
      bar.callIv ?? '',
      bar.putIv ?? '',
      bar.callOi,
      bar.putOi,
      bar.ratio ?? ''
    ].join(',')
  );
  return [header, ...body].join('\n');
}

/** `skew-NIFTY-2026-09-03-1030.csv` — the session *and* the capture. */
export function csvFilename(symbol: string, frame: SkewFrame | undefined): string {
  if (!frame) return `skew-${symbol}.csv`;
  const stamp = frame.t.slice(0, 16).replace('T', '-').replace(':', '');
  return `skew-${symbol}-${stamp}.csv`;
}
