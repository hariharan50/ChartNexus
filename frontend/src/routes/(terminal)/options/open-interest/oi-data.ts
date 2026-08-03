/**
 * Wire types and pure client-side derivations for the Open Interest tool.
 *
 * The backend already ships a fully-derived payload; this module re-derives the
 * per-strike bars and window totals on the client so a strike filter or a
 * timeline scrub is instant and never waits on a round trip. Everything here is
 * pure and keyed off the payload, safe to run inside a Svelte `$derived`.
 */

import { apiFetch } from '$shared/api/client';

export interface OiSeriesFrame {
  t: string;
  strikes: number[];
  /** OI aligned to `strikes`; `null` marks a leg that was not listed. */
  call: (number | null)[];
  put: (number | null)[];
}

export interface OiStrike {
  strike: number;
  call_oi_open: number;
  call_oi_now: number;
  call_oi_chg: number;
  call_oi_chg_pct: number;
  put_oi_open: number;
  put_oi_now: number;
  put_oi_chg: number;
  put_oi_chg_pct: number;
}

export interface OiSentiment {
  label: string;
  bullish_pct: number;
  insight: string;
  analysis: string;
}

export interface OiView {
  instrument_id: string;
  symbol: string;
  spot: number;
  atm_strike: number;
  max_pain: number;
  lot_size: number | null;
  expiry_date: string | null;
  pcr_oi: number;
  pcr_change: number;
  open_ts: string;
  now_ts: string;
  data_quality: 'intraday' | 'live_proxy' | 'empty';
  total_call_oi: number;
  total_put_oi: number;
  total_call_oi_chg: number;
  total_put_oi_chg: number;
  sentiment: OiSentiment;
  strikes: OiStrike[];
  series: OiSeriesFrame[];
}

export function getOpenInterest(instrument: string, fetcher?: typeof fetch): Promise<OiView> {
  return apiFetch<OiView>({ url: `/options-lab/oi/${encodeURIComponent(instrument)}`, fetcher });
}

/** The instrument catalog the sidebar cycles through (wraparound). */
export interface Instrument {
  id: number;
  short: string;
  badge: string;
  symbol: string;
}

export const OI_INSTRUMENTS: Instrument[] = [
  { id: 1, short: 'NIFTY', badge: '50', symbol: 'NIFTY' },
  { id: 2, short: 'SENSEX', badge: 'BSE', symbol: 'SENSEX' },
  { id: 3, short: 'BANKNIFTY', badge: 'BNK', symbol: 'BANKNIFTY' }
];

export const CALL_COLOR = '#22c55e';
export const PUT_COLOR = '#ef4444';

/** Chart modes. */
export type OiMode = 'change_total' | 'change' | 'total';

/** Compact Indian OI units, or integer lots when `showLot`. */
export function fmtOi(value: number, showLot = false, lotSize = 75): string {
  if (showLot && lotSize > 0) return Math.round(value / lotSize).toLocaleString('en-IN');
  const abs = Math.abs(value);
  const sign = value < 0 ? '-' : '';
  if (abs >= 1e7) return `${sign}${(abs / 1e7).toFixed(2)}Cr`;
  if (abs >= 1e5) return `${sign}${(abs / 1e5).toFixed(2)}L`;
  if (abs >= 1e3) return `${sign}${(abs / 1e3).toFixed(2)}K`;
  return `${sign}${Math.round(abs)}`;
}

/** Same as {@link fmtOi} but always prefixes a `+` on non-negatives. */
export function fmtSigned(value: number, showLot = false, lotSize = 75): string {
  return (value >= 0 ? '+' : '') + fmtOi(value, showLot, lotSize);
}

/**
 * Fractional category index for a price, so a spot/future line can land between
 * two strike columns rather than snapping onto one.
 */
export function priceIndex(strikes: number[], price: number): number {
  if (strikes.length === 0) return 0;
  if (price <= strikes[0]!) return 0;
  const last = strikes.length - 1;
  if (price >= strikes[last]!) return last;
  for (let i = 0; i < last; i++) {
    const a = strikes[i]!;
    const b = strikes[i + 1]!;
    if (price >= a && price <= b) return i + (price - a) / (b - a);
  }
  return last;
}

/** Index of the snapshot ~`minutes` before `nowIdx` (0 for "all"). */
export function baselineIndex(
  series: OiSeriesFrame[],
  nowIdx: number,
  minutes: number | 'all'
): number {
  if (minutes === 'all' || series.length === 0) return 0;
  const nowT = new Date(series[nowIdx]!.t).getTime();
  const target = nowT - minutes * 60_000;
  let idx = 0;
  for (let i = 0; i <= nowIdx && i < series.length; i++) {
    if (new Date(series[i]!.t).getTime() <= target) idx = i;
  }
  return idx;
}

/** A short IST clock label like `10:03 am`. */
export function timeLabel(iso: string): string {
  return new Intl.DateTimeFormat('en-US', {
    timeZone: 'Asia/Kolkata',
    hour: 'numeric',
    minute: '2-digit',
    hour12: true
  })
    .format(new Date(iso))
    .toLowerCase();
}

/** A per-strike bar row the chart and table both render. */
export interface OiBar {
  strike: number;
  callNow: number;
  putNow: number;
  callOpen: number;
  putOpen: number;
  callChg: number;
  putChg: number;
  atm: boolean;
  maxPain: boolean;
}

/** Smallest positive gap between strikes; the strike-filter step. */
export function inferStep(strikes: number[]): number {
  let step = Infinity;
  for (let i = 1; i < strikes.length; i++) {
    const d = strikes[i]! - strikes[i - 1]!;
    if (d > 0 && d < step) step = d;
  }
  return Number.isFinite(step) ? step : 50;
}

/** Keep strikes within `span` steps either side of ATM (`span = 0` → all). */
export function withinWindow(strikes: number[], atm: number, step: number, span: number): number[] {
  if (span <= 0) return strikes;
  const reach = step * span;
  return strikes.filter((s) => Math.abs(s - atm) <= reach + 1e-6);
}

function frameOi(frame: OiSeriesFrame | undefined, strike: number, side: 'call' | 'put'): number {
  if (!frame) return 0;
  const i = frame.strikes.indexOf(strike);
  if (i < 0) return 0;
  return frame[side][i] ?? 0;
}

/**
 * Per-strike bars for the visible strikes. When the payload carries a series
 * (≥2 frames) the "open" and "now" ends come from the chosen frames — so a
 * timeline scrub re-derives instantly; otherwise the static payload fields are
 * used.
 */
export function deriveBars(
  view: OiView,
  visible: number[],
  openFrame?: OiSeriesFrame,
  nowFrame?: OiSeriesFrame
): OiBar[] {
  const byStrike = new Map(view.strikes.map((r) => [r.strike, r]));
  const useSeries = Boolean(openFrame && nowFrame);

  return visible.map((strike) => {
    const row = byStrike.get(strike);
    const callNow = useSeries ? frameOi(nowFrame, strike, 'call') : (row?.call_oi_now ?? 0);
    const putNow = useSeries ? frameOi(nowFrame, strike, 'put') : (row?.put_oi_now ?? 0);
    const callOpen = useSeries ? frameOi(openFrame, strike, 'call') : (row?.call_oi_open ?? 0);
    const putOpen = useSeries ? frameOi(openFrame, strike, 'put') : (row?.put_oi_open ?? 0);
    return {
      strike,
      callNow,
      putNow,
      callOpen,
      putOpen,
      callChg: callNow - callOpen,
      putChg: putNow - putOpen,
      atm: strike === view.atm_strike,
      maxPain: strike === view.max_pain
    };
  });
}

export interface OiTotals {
  callNow: number;
  putNow: number;
  callOpen: number;
  putOpen: number;
  callChg: number;
  putChg: number;
  pcr: number;
  pcrChange: number;
}

/** Window totals over the FULL chain (not just the visible strikes). */
export function windowTotals(
  view: OiView,
  openFrame?: OiSeriesFrame,
  nowFrame?: OiSeriesFrame
): OiTotals {
  let callNow: number;
  let putNow: number;
  let callOpen: number;
  let putOpen: number;

  if (openFrame && nowFrame) {
    const sum = (f: OiSeriesFrame, side: 'call' | 'put') =>
      f[side].reduce((a: number, v) => a + (v ?? 0), 0);
    callNow = sum(nowFrame, 'call');
    putNow = sum(nowFrame, 'put');
    callOpen = sum(openFrame, 'call');
    putOpen = sum(openFrame, 'put');
  } else {
    callNow = view.total_call_oi;
    putNow = view.total_put_oi;
    callOpen = view.total_call_oi - view.total_call_oi_chg;
    putOpen = view.total_put_oi - view.total_put_oi_chg;
  }

  const pcr = callNow > 0 ? putNow / callNow : 0;
  const pcrOpen = callOpen > 0 ? putOpen / callOpen : 0;
  return {
    callNow,
    putNow,
    callOpen,
    putOpen,
    callChg: callNow - callOpen,
    putChg: putNow - putOpen,
    pcr,
    pcrChange: pcr - pcrOpen
  };
}
