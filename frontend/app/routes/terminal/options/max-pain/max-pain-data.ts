/**
 * The max-pain curve, derived on the client from the Open Interest payload.
 *
 * There is no max-pain endpoint and does not need to be one:
 * `GET /options-lab/oi/{id}` already ships per-strike open interest for the
 * whole chain, and the curve is arithmetic over it. That is what
 * `docupdateimp/CALCULATIONS_ARCHITECTURE.md` prescribes — "Max Pain curve runs
 * client-side from raw arrays the backend ships".
 *
 * Everything here is pure, so the arithmetic is testable without a canvas.
 */

import { apiFetch } from '$shared/api/client';
import type { OiStrike } from '../open-interest/oi-data';

/** What every option holder would lose if the market settled at `strike`. */
export interface PainPoint {
  strike: number;
  callPain: number;
  putPain: number;
  total: number;
}

/**
 * Pain at every listed strike, priced against the **whole** chain.
 *
 *     pain(P) = Σ CE_OI · max(0, P − K) + Σ PE_OI · max(0, K − P)
 *
 * Lot size is deliberately absent, matching the documented formula. Including
 * it multiplies every bar by the same constant: the shape and the argmin are
 * identical, only the axis labels change.
 *
 * The candidates are priced against all strikes even when the chart draws a
 * narrow window. Max pain is a property of the full book — summing only nearby
 * strikes would yield a different argmin from the `max_pain` the payload
 * already reports, and the marker would visibly disagree with the bars it sits
 * among.
 */
export function painCurve(strikes: OiStrike[]): PainPoint[] {
  return strikes
    .map((candidate) => {
      let callPain = 0;
      let putPain = 0;
      for (const row of strikes) {
        // A call is only worth exercising above its strike, a put below.
        if (candidate.strike > row.strike) {
          callPain += row.call_oi_now * (candidate.strike - row.strike);
        } else if (candidate.strike < row.strike) {
          putPain += row.put_oi_now * (row.strike - candidate.strike);
        }
      }
      return { strike: candidate.strike, callPain, putPain, total: callPain + putPain };
    })
    .sort((a, b) => a.strike - b.strike);
}

/** The strike where total pain is least — the curve's own answer. */
export function maxPainStrike(curve: PainPoint[]): number | null {
  if (curve.length === 0) return null;
  return curve.reduce((best, point) => (point.total < best.total ? point : best)).strike;
}

/**
 * The curve narrowed to what the chart should draw.
 *
 * `visible` is the ±N window the sidebar chose. Max pain can fall outside it —
 * it answers to the whole chain, not the filter — and a Max Pain chart that
 * does not show max pain is broken, so the window stretches to reach it rather
 * than dropping the marker.
 */
export function visibleCurve(curve: PainPoint[], visible: number[], maxPain: number): PainPoint[] {
  if (visible.length === 0) return curve;

  const low = Math.min(...visible, maxPain);
  const high = Math.max(...visible, maxPain);
  return curve.filter((point) => point.strike >= low && point.strike <= high);
}

/** True when the window had to stretch, so the caption can say so. */
export function windowWidened(visible: number[], maxPain: number): boolean {
  if (visible.length === 0) return false;
  return maxPain < Math.min(...visible) || maxPain > Math.max(...visible);
}

/**
 * Pain formatted for an axis or a tooltip: `1.29B`, `7.18B`, `60B`.
 *
 * Its own scale rather than `fmtOi`'s: open interest tops out in crore, whereas
 * pain is open interest multiplied by a price distance and runs three orders
 * higher. Reusing the OI formatter would print every bar as a five-digit crore
 * figure.
 */
export function fmtPain(value: number): string {
  const abs = Math.abs(value);
  const sign = value < 0 ? '-' : '';
  if (abs >= 1e12) return `${sign}${(abs / 1e12).toFixed(2)}T`;
  if (abs >= 1e9) return `${sign}${(abs / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${sign}${(abs / 1e6).toFixed(2)}M`;
  if (abs >= 1e3) return `${sign}${(abs / 1e3).toFixed(2)}K`;
  return `${sign}${Math.round(abs)}`;
}

/**
 * The five readings the gauge can give, left to right along the arc.
 *
 * TradingView's wording, because the dial is TradingView's: a reader who has
 * seen one knows immediately which end is which.
 */
export type MaxPainZone = 'Strong sell' | 'Sell' | 'Neutral' | 'Buy' | 'Strong buy';

const ZONES: MaxPainZone[] = ['Strong sell', 'Sell', 'Neutral', 'Buy', 'Strong buy'];

/** How the market sits relative to the level that hurts most holders. */
export interface MaxPainBias {
  label: MaxPainZone;
  caption: string;
  insight: string;
  /** Signed gap between spot and max pain, in percent. */
  gapPct: number;
  /**
   * Where the gauge pointer sits, 0–1 across the arc.
   *
   * Signed, unlike the magnitude a ring could show: 0.5 is spot exactly on max
   * pain, 0 is a full move below it and 1 a full move above. Direction is the
   * whole signal on this page, so it has to survive into the reading.
   */
  position: number;
}

/**
 * A gap this wide, as a fraction of max pain, reaches the end of the arc.
 *
 * 2% is a large move for an index — a 24,600 max pain would need spot near
 * 25,100. Scaling to it keeps an ordinary intraday gap reading as the small
 * signal it is: the reference's 36-point gap is 0.15%, barely a tick of arc.
 */
const FULL_ARC_PCT = 2;

/** Maps a signed percentage gap onto the gauge's 0–1 axis. */
function arcPosition(gapPct: number): number {
  const half = gapPct / FULL_ARC_PCT / 2;
  return 0.5 + Math.min(0.5, Math.max(-0.5, half));
}

/**
 * Which of the five zones a pointer position falls in.
 *
 * Derived from `position` and nothing else — deliberately. The zone name and
 * the needle are two renderings of one number, and the only way they can ever
 * disagree is if one of them is computed from the gap directly. Reading the
 * fifth off the arc makes that impossible by construction.
 *
 * The boundaries land at gaps of ±0.4% and ±1.2% of max pain, given the ±2%
 * full-arc scale above.
 */
export function zoneAt(position: number): MaxPainZone {
  const clamped = Math.min(1, Math.max(0, position));
  // `min` keeps a position of exactly 1 in the last zone rather than a sixth.
  return ZONES[Math.min(ZONES.length - 1, Math.floor(clamped * ZONES.length))]!;
}

/**
 * Reads the spot-versus-max-pain gap.
 *
 * Uses **spot**, not the futures price. The reference's panel says "Future
 * price above Max Pain" while the row beneath it reads "Spot Price" — it
 * contradicts itself. Spot is the field `get_oi_view` returns, and max-pain
 * theory is about where the underlying settles, so both say spot here.
 */
export function maxPainBias(spot: number, maxPain: number): MaxPainBias {
  if (!Number.isFinite(spot) || !Number.isFinite(maxPain) || maxPain <= 0) {
    return {
      label: 'Neutral',
      caption: 'Awaiting market data',
      insight: 'No chain data yet, so there is nothing to compare against max pain.',
      gapPct: 0,
      // Dead centre, not zero: an empty gauge would read as a full bearish
      // move rather than as "nothing to say".
      position: 0.5
    };
  }

  const gapPct = ((spot - maxPain) / maxPain) * 100;
  const position = arcPosition(gapPct);
  const label = zoneAt(position);

  if (label === 'Neutral') {
    return {
      label,
      caption: 'Spot sitting on Max Pain',
      insight:
        'Spot is effectively at the max pain level — the point where the most option value expires worthless. Writers have little left to defend.',
      gapPct,
      position
    };
  }

  const above = gapPct > 0;
  return {
    label,
    caption: above ? 'Spot above Max Pain' : 'Spot below Max Pain',
    insight: above
      ? `Spot is ${Math.abs(gapPct).toFixed(2)}% above max pain. Writers gain from a drift back down, so this level tends to act as a magnet into expiry.`
      : `Spot is ${Math.abs(gapPct).toFixed(2)}% below max pain. Writers gain from a drift back up, so this level tends to act as a magnet into expiry.`,
    gapPct,
    position
  };
}

// -- the intraday series ------------------------------------------------------

/**
 * Max pain through the session, from the archive.
 *
 * Unlike the curve above, this cannot be derived on the client: it needs one
 * priced chain per capture, and the payload that would carry eighty of those is
 * the whole archive. The backend reads the `max_pain_strike` the ingest worker
 * already stored at capture time.
 */
export interface MaxPainSeriesView {
  instrument_id: string;
  symbol: string;
  expiry_date: string | null;
  lot_size: number | null;
  spot: number;
  open_ts: string;
  now_ts: string;
  /** `intraday` | `live_proxy` | `empty` — how much session there really is. */
  data_quality: string;
  open_is_estimated: boolean;
  t: string[];
  /** The tradable future. `null` on the reconstructed 09:15 frame. */
  fut: (number | null)[];
  /** `null`, never 0, where a capture could not be priced. */
  max_pain: (number | null)[];
}

export function getMaxPainSeries(
  instrument: string,
  opts: { date?: string | undefined } = {},
  fetcher?: typeof fetch
): Promise<MaxPainSeriesView> {
  return apiFetch<MaxPainSeriesView>({
    url: `/options-lab/max-pain-series/${encodeURIComponent(instrument)}`,
    params: opts.date ? { date: opts.date } : {},
    fetcher
  });
}

/** Which way max pain has moved today, and what spot is doing about it. */
export type Drift = 'up' | 'down' | 'unchanged';
export type Approach = 'converging' | 'diverging' | 'steady';

export interface Convergence {
  /** Latest max pain, and the price being read against it. */
  maxPain: number;
  price: number;
  /** `price − maxPain`: positive means spot is above the pin. */
  distance: number;
  distancePct: number;
  /** Where max pain opened, and how far it has travelled since. */
  openMaxPain: number;
  shift: number;
  drift: Drift;
  /** Whether the gap has narrowed since the open. */
  approach: Approach;
}

/**
 * The reading the chart is for.
 *
 * A snapshot says where max pain is; this says where it is *going* and whether
 * price is closing on it. Max pain migrating toward spot is writers
 * repositioning, and it is the part a single bar chart cannot show.
 *
 * Returns `undefined` rather than a zeroed reading when there is not enough
 * session to compare two ends of — a "0 points, steady" card would look like a
 * finding rather than an absence.
 */
export function convergence(view: MaxPainSeriesView | undefined): Convergence | undefined {
  if (!view) return undefined;

  const pains = view.max_pain;
  const lastIdx = lastDefined(pains);
  const firstIdx = firstDefined(pains);
  if (lastIdx === null || firstIdx === null) return undefined;

  const maxPain = pains[lastIdx]!;
  const openMaxPain = pains[firstIdx]!;
  if (maxPain <= 0) return undefined;

  // The future where one was recorded, else the chain's spot. The future is
  // the tradable instrument and the one the chart plots, so the card must read
  // against the same number the eye is following.
  const priceIdx = lastDefined(view.fut);
  const price = priceIdx === null ? view.spot : view.fut[priceIdx]!;
  if (!Number.isFinite(price) || price <= 0) return undefined;

  const distance = price - maxPain;
  const shift = maxPain - openMaxPain;

  const openPriceIdx = firstDefined(view.fut);
  const openPrice = openPriceIdx === null ? price : view.fut[openPriceIdx]!;
  const openGap = Math.abs(openPrice - openMaxPain);
  const nowGap = Math.abs(distance);

  return {
    maxPain,
    price,
    distance,
    distancePct: (distance / maxPain) * 100,
    openMaxPain,
    shift,
    drift: shift > 0 ? 'up' : shift < 0 ? 'down' : 'unchanged',
    approach: approachOf(openGap, nowGap, maxPain)
  };
}

/**
 * Below this the gap has not really changed.
 *
 * A quarter of a percent **of the index level** — about 58 points on a 23,350
 * NIFTY, or a little over one strike. Scaled to the index rather than to the
 * gap itself on purpose: a gap that opens at 100 points and sits at 102 has not
 * changed regime, but a dead zone derived from that 100 would call the 2-point
 * wobble a divergence. Without this every tick flips the card between
 * converging and diverging, which is noise dressed as a signal.
 */
const APPROACH_DEAD_ZONE_PCT = 0.25;

function approachOf(openGap: number, nowGap: number, level: number): Approach {
  const moved = openGap - nowGap;
  const deadZone = Math.abs(level) * (APPROACH_DEAD_ZONE_PCT / 100);
  if (Math.abs(moved) < deadZone) return 'steady';
  return moved > 0 ? 'converging' : 'diverging';
}

function firstDefined(values: (number | null)[]): number | null {
  const index = values.findIndex((value) => value != null && Number.isFinite(value));
  return index === -1 ? null : index;
}

function lastDefined(values: (number | null)[]): number | null {
  for (let index = values.length - 1; index >= 0; index -= 1) {
    const value = values[index];
    if (value != null && Number.isFinite(value)) return index;
  }
  return null;
}
