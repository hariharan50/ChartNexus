/**
 * Wire types and pure client-side derivations for the Open Interest tool.
 *
 * The backend already ships a fully-derived payload; this module re-derives the
 * per-strike bars and window totals on the client so a strike filter or a
 * timeline scrub is instant and never waits on a round trip. Everything here is
 * pure and keyed off the payload, safe to run inside a Svelte `$derived`.
 */

import { apiFetch } from '$shared/api/client';
import {
  isTradingWindow,
  SESSION_CLOSE_MIN,
  SESSION_MINUTES,
  SESSION_OPEN_MIN
} from '$shared/formatting/ist-clock';

export interface OiSeriesFrame {
  t: string;
  strikes: number[];
  /** OI aligned to `strikes`; `null` marks a leg that was never listed. */
  call: (number | null)[];
  put: (number | null)[];
  /**
   * What the market looked like at this instant.
   *
   * Absent on the live tier, whose two frames are synthesised from a single
   * chain — callers fall back to the payload-level values. Without these,
   * scrubbing would move the bars while the spot line and max-pain marker
   * stayed pinned to the newest snapshot.
   */
  spot?: number | null;
  atm?: number | null;
  max_pain?: number | null;
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
  /**
   * The 09:15 frame was derived from the broker's day-change field rather than
   * read from a stored capture — which is what happens whenever ingest started
   * after the bell. The values are real; only the intervening frames are
   * missing.
   */
  open_is_estimated: boolean;
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

/** How often the page re-fetches. Also rendered, so the two cannot drift apart. */
export const REFETCH_MS = 15_000;

/** Past this the feed is treated as stalled rather than merely between polls. */
export const STALE_AFTER_MS = REFETCH_MS * 3;

/**
 * How long ago the data on screen arrived, e.g. `just now` / `12s ago`.
 *
 * The reason this is on screen at all: when nothing is writing snapshots the
 * page polls faithfully and receives identical bytes every time, so it looks
 * frozen with no way to tell a quiet market from a broken pipeline. This makes
 * the difference legible.
 */
export function freshnessLabel(updatedAt: number, now: number): string {
  if (!updatedAt) return 'never';
  const seconds = Math.max(0, Math.round((now - updatedAt) / 1000));
  if (seconds < 5) return 'just now';
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  return `${Math.floor(minutes / 60)}h ago`;
}

/**
 * How far behind the newest *frame* may fall before the feed is stalled.
 *
 * Deliberately generous against the one-minute capture cadence: a couple of
 * missed ticks is a slow broker, five minutes of nothing is a dead pipeline.
 */
export const FEED_STALE_AFTER_MS = 5 * 60_000;

/**
 * Age of the newest point in the payload, or `null` when it is current.
 *
 * Distinct from {@link freshnessLabel}, and the distinction is the whole point.
 * That one times the *HTTP response*; this one times the *data inside it*. When
 * the ingest worker dies the endpoint keeps answering in milliseconds with a
 * series that stopped growing an hour ago — the response is fresh, the data is
 * not, and only this reads as stale. A chart that looks live while showing
 * hour-old open interest is worse than one that admits it has no news.
 *
 * `null` outside trading hours: after the close the series is *supposed* to
 * stop, and flagging it all evening trains people to ignore the warning.
 */
export function feedAgeMs(nowTs: string | undefined, now: number): number | null {
  if (!nowTs || !isTradingWindow(now)) return null;
  const age = now - Date.parse(nowTs);
  return age > FEED_STALE_AFTER_MS ? age : null;
}

/** `67m behind` — how far the drawn series lags the clock beside it. */
export function feedAgeLabel(ageMs: number): string {
  const minutes = Math.floor(ageMs / 60_000);
  if (minutes < 60) return `${minutes}m behind`;
  return `${Math.floor(minutes / 60)}h ${minutes % 60}m behind`;
}

/** `6 Aug` in IST — the trading date, not the viewer's. */
export function dateLabel(at: number): string {
  return new Intl.DateTimeFormat('en-IN', {
    timeZone: 'Asia/Kolkata',
    day: 'numeric',
    month: 'short'
  }).format(new Date(at));
}

/** `1:12:01 pm` in IST, seconds included so it visibly ticks. */
export function clockLabel(at: number): string {
  return new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Asia/Kolkata',
    // `numeric`, not `2-digit`: a 12-hour clock does not pad the hour, and
    // `01:12 pm` reads as a mistake.
    hour: 'numeric',
    minute: '2-digit',
    second: '2-digit',
    hour12: true
  })
    .format(new Date(at))
    .toLowerCase();
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

/** One mark under the time slider. */
export interface SliderTick {
  /** Frame this tick sits on. */
  index: number;
  /** Position along the track, 0–100. */
  pct: number;
  /** `null` for the unlabelled half-hour marks. */
  label: string | null;
}

const HOUR_LABEL = new Intl.DateTimeFormat('en-US', {
  timeZone: 'Asia/Kolkata',
  hour: 'numeric',
  hour12: true
});

/** Minutes past IST midnight for an instant. */
function istMinutes(iso: string): number {
  const at = new Date(iso);
  const ist = new Date(at.getTime() + (330 + at.getTimezoneOffset()) * 60_000);
  return ist.getHours() * 60 + ist.getMinutes();
}

/** IST half-hour bucket for an instant — `hour * 2`, plus one past the half. */
function halfHour(iso: string): number {
  const minutes = istMinutes(iso);
  return Math.floor(minutes / 60) * 2 + (minutes % 60 >= 30 ? 1 : 0);
}

const SESSION_SPAN_MIN = SESSION_MINUTES;

/** Where an instant sits on a track spanning 09:15–15:40 IST, 0–100. */
function sessionPct(iso: string): number {
  const offset = ((istMinutes(iso) - SESSION_OPEN_MIN) / SESSION_SPAN_MIN) * 100;
  // Clamped rather than dropped: a capture a minute either side of the bell is
  // a real observation, and it belongs at the end of the track, not off it.
  return Math.min(100, Math.max(0, offset));
}

/**
 * Each frame's position on a **session-length** track, as a percentage.
 *
 * The counterpart to {@link axisTicks}'s index positioning, and the right
 * choice when the question is "what did the book look like at this time"
 * rather than "what changed between these two snapshots". Index positioning
 * stretches whatever was recorded across the full width, so a session that
 * only started archiving at 1 pm draws a track labelled 1 pm to 3 pm and
 * silently reads as a whole trading day. On a session track the same data
 * occupies the right-hand third, and the empty left-hand two-thirds is the
 * honest picture: there is no morning.
 */
export function sessionPositions(times: readonly string[]): number[] {
  return times.map(sessionPct);
}

/**
 * Hour marks across the whole trading session, at their clock positions.
 *
 * Fixed geometry — it does not depend on what was recorded, which is the
 * point: the track means the same thing on a full day and on a day whose
 * ingest started late.
 *
 * The hour names are built arithmetically rather than through `Intl`. These
 * are IST wall-clock hours with no instant behind them, and manufacturing a
 * `Date` to format is how an off-by-one timezone bug gets into a label that
 * only ever needed "10 am".
 */
export function sessionTicks(): SliderTick[] {
  // The bell and the close get a mark but no text: the caller renders both
  // times either side of the track, and at 375px "9:15 am" and "10 am" are
  // 45px apart — they overprint into `9:15 am10 am`.
  const ticks: SliderTick[] = [{ index: SESSION_OPEN_MIN, pct: 0, label: null }];

  for (let hour = 10; hour <= 15; hour++) {
    const minutes = hour * 60;
    if (minutes <= SESSION_OPEN_MIN || minutes >= SESSION_CLOSE_MIN) continue;
    ticks.push({
      index: minutes,
      pct: ((minutes - SESSION_OPEN_MIN) / SESSION_SPAN_MIN) * 100,
      label: `${hour > 12 ? hour - 12 : hour} ${hour < 12 ? 'am' : 'pm'}`
    });
  }

  ticks.push({ index: SESSION_CLOSE_MIN, pct: 100, label: null });
  return ticks;
}

/**
 * Hour and half-hour marks for the timeline, one per frame that opens a new
 * bucket.
 *
 * Positions are **frame-index fractions, never clock fractions**, because the
 * handle also moves by index: one step of the slider is one snapshot, not one
 * unit of time. With an even ingest cadence the two coincide; after a gap they
 * diverge, and index-positioning is the one that keeps a tick under the frame
 * it names. Each label is formatted from its own frame's timestamp — nothing is
 * interpolated, so a gap shows up as a wider spacing rather than a wrong time.
 */
/**
 * Closest two hour labels may sit, as a percentage of the track.
 *
 * An ingest gap crushes many hours into a few pixels — a session recorded from
 * 1 pm with a derived 9:15 baseline puts "9 am" and "1 pm" 1.8% apart, and they
 * overprint into `9 am1 pm`. The tick mark still gets drawn; only the text is
 * dropped, so no position is silently lost.
 */
const MIN_LABEL_GAP_PCT = 7;

/**
 * Typed on the timestamp alone, not on `OiSeriesFrame`: every Options Lab tool
 * scrubs a session, and the tick geometry is the same whether the frames carry
 * open interest, gamma or nothing but a clock.
 */
export function axisTicks(series: readonly { t: string }[]): SliderTick[] {
  if (series.length < 2) return [];

  const span = series.length - 1;
  const ticks: SliderTick[] = [];
  let previous = -1;
  let lastLabelledPct = Number.NEGATIVE_INFINITY;

  for (let i = 0; i < series.length; i++) {
    const bucket = halfHour(series[i]!.t);
    if (bucket === previous) continue;
    previous = bucket;

    const pct = (i / span) * 100;
    // Only the top of each hour is labelled; the half-hours are bare marks,
    // which is as much text as fits at 375px.
    const onTheHour = bucket % 2 === 0;
    const roomForText = pct - lastLabelledPct >= MIN_LABEL_GAP_PCT;
    const label =
      onTheHour && roomForText ? HOUR_LABEL.format(new Date(series[i]!.t)).toLowerCase() : null;
    if (label !== null) lastLabelledPct = pct;

    ticks.push({ index: i, pct, label });
  }

  return ticks;
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

  // Anchored to the frame being shown, not to the payload — scrubbing back to
  // 10:30 must highlight 10:30's ATM strike, not the latest one.
  const atmStrike = nowFrame?.atm ?? view.atm_strike;
  const maxPainStrike = nowFrame?.max_pain ?? view.max_pain;

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
      atm: strike === atmStrike,
      maxPain: strike === maxPainStrike
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
