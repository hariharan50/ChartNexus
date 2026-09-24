/**
 * Wire types and pure derivations for the Price vs OI tool.
 *
 * The backend serves one strike's whole session in a single payload — call/put
 * price, OI, day OI change, the straddle and the per-strike PCR on a shared time
 * axis, plus the strike ladder for the sidebar. Everything the six charts draw is
 * a pure client-side derivation over that payload, so the timeframe re-buckets
 * without a round trip and the normalisation is testable without a canvas.
 */

import { apiFetch } from '$shared/api/client';

// The Price vs OI tool reads the same session the OI-family pages do, so it
// reuses their session/clock/format helpers rather than restating them.
export {
  CALL_COLOR,
  PUT_COLOR,
  OI_INSTRUMENTS,
  REFETCH_MS,
  STALE_AFTER_MS,
  clockLabel,
  dateLabel,
  freshnessLabel,
  fmtOi,
  timeLabel,
  type Instrument
} from '../open-interest/oi-data';

export {
  bucketIndices,
  DEFAULT_TIMEFRAME,
  expiryLabel,
  fmtPrice,
  pick,
  TIMEFRAMES,
  type Timeframe
} from '../atm-straddle/straddle-data';

/** One strike's whole-session price/OI series, aligned on `t`. */
export interface StrikeSeriesView {
  instrument_id: string;
  symbol: string;
  expiry_date: string | null;
  lot_size: number | null;
  spot: number;
  atm_strike: number | null;
  /** The strike this payload plots. */
  strike: number;
  /** The ladder the sidebar chooses from. */
  strikes: number[];
  open_ts: string;
  now_ts: string;
  data_quality: 'intraday' | 'empty';
  open_is_estimated: boolean;
  t: string[];
  /** `null` where a leg was absent from the capture; a genuine 0 is kept. */
  ce_price: (number | null)[];
  pe_price: (number | null)[];
  ce_oi: (number | null)[];
  pe_oi: (number | null)[];
  ce_oi_change: (number | null)[];
  pe_oi_change: (number | null)[];
  straddle: (number | null)[];
  /** `null`, never 0, at an empty call-OI denominator. */
  pcr: (number | null)[];
}

export function getStrikeSeries(
  instrument: string,
  strike?: number | undefined,
  opts: { date?: string | undefined; expiry?: string | undefined } = {},
  fetcher?: typeof fetch
): Promise<StrikeSeriesView> {
  return apiFetch<StrikeSeriesView>({
    url: `/options-lab/strike-series/${encodeURIComponent(instrument)}`,
    // Omit `strike` for the at-the-money default the backend fills in.
    params: {
      ...(strike != null ? { strike } : {}),
      ...(opts.date ? { date: opts.date } : {}),
      ...(opts.expiry ? { expiry: opts.expiry } : {})
    },
    fetcher
  });
}

/**
 * Each point as a fraction of the session-open value: `(v - v0) / v0`.
 *
 * The "Call vs Put" charts plot this so a call worth 150 and a put worth 90 can
 * be compared on one centred axis — both read as "how far from where it opened".
 * The open is the first real point; a `null` point stays `null`, and a zero or
 * missing open voids the whole series (there is nothing to divide by). The
 * absolute values are carried separately for the tooltip and end-pill.
 */
export function normalizeFromOpen(values: (number | null)[]): (number | null)[] {
  const open = values.find((value) => value != null) ?? null;
  if (open == null || open === 0) return values.map(() => null);
  return values.map((value) => (value == null ? null : (value - open) / open));
}

/** A signed percentage, e.g. `+12.4%` — the normalised axis label and tooltip. */
export function fmtPct(value: number): string {
  return `${value >= 0 ? '+' : ''}${(value * 100).toFixed(1)}%`;
}

/** The put/call ratio — two decimals, the reference's precision. */
export function fmtPcr(value: number): string {
  return value.toFixed(2);
}

/** `18 Aug 2026 (4d)` — kept local so a null expiry still reads sensibly. */
export function strikeLabel(strike: number): string {
  return String(strike);
}
