/**
 * Wire types and pure derivations for the Gamma Exposure tool.
 *
 * The endpoint ships a full session of per-strike exposure in one payload, so
 * the strike filter and the time scrub are both applied here — neither costs a
 * round trip. Same trade as the Put-Call Ratio tool, for the same reason: what
 * the server sends is small enough that the client can afford to hold it all.
 *
 * Everything is pure, so the arithmetic is testable without a canvas.
 */

import { apiFetch } from '$shared/api/client';

/** One capture's profile, with the four levels read off it. */
export interface GexFrame {
  t: string;
  spot: number;
  atm: number | null;
  /**
   * Aligned to {@link GexView.strikes}, in **crore per 1% move in spot**.
   *
   * Signed for the dealer view: calls positive, puts negative. The server owns
   * both the unit and the sign so two clients cannot disagree about them.
   */
  call_gex: number[];
  put_gex: number[];
  net_total: number;
  abs_total: number;
  /** Every level is nullable — a one-sided book genuinely has no wall. */
  call_wall: number | null;
  put_wall: number | null;
  gamma_flip: number | null;
  net_cross: number | null;
}

export interface GexView {
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
  /** 0–1. Below 1, some legs had no quoted volatility and contributed zero. */
  iv_coverage: number;
  strikes: number[];
  t: string[];
  frames: GexFrame[];
}

export function getGex(
  instrument: string,
  opts: { date?: string | undefined } = {},
  fetcher?: typeof fetch
): Promise<GexView> {
  return apiFetch<GexView>({
    url: `/options-lab/gex/${encodeURIComponent(instrument)}`,
    params: opts.date ? { date: opts.date } : {},
    fetcher
  });
}

/** How the chart arranges the profile. */
export type GexLayout = 'horizontal' | 'vertical' | 'callPut';

export const LAYOUTS: readonly { value: GexLayout; label: string }[] = [
  { value: 'horizontal', label: 'Horizontal' },
  { value: 'vertical', label: 'Vertical' },
  { value: 'callPut', label: 'Call-Put' }
];

/** Strikes either side of ATM the sidebar offers. */
export const STRIKE_FILTERS: readonly { label: string; value: 'all' | number }[] = [
  { label: 'All', value: 'all' },
  { label: '5', value: 5 },
  { label: '10', value: 10 },
  { label: '20', value: 20 }
];

/** One strike's row, once the window and the frame have both been applied. */
export interface GexBar {
  strike: number;
  callGex: number;
  putGex: number;
  net: number;
  abs: number;
}

/**
 * The rows to draw: one frame, narrowed to the chosen strikes.
 *
 * `visible` is a set of strike prices rather than indices so the caller can
 * build it with the same `withinWindow` the other Options Lab pages use, and
 * the two windows are guaranteed to agree.
 */
export function frameBars(strikes: number[], frame: GexFrame, visible: Set<number>): GexBar[] {
  const bars: GexBar[] = [];
  for (let i = 0; i < strikes.length; i++) {
    const strike = strikes[i]!;
    if (!visible.has(strike)) continue;
    const callGex = frame.call_gex[i] ?? 0;
    const putGex = frame.put_gex[i] ?? 0;
    bars.push({
      strike,
      callGex,
      putGex,
      net: callGex + putGex,
      // Recomputed from the two sides rather than sent: it is |call| + |put| by
      // definition, and a third array per frame would be a second source of
      // truth for a figure that cannot disagree with its own inputs.
      abs: Math.abs(callGex) + Math.abs(putGex)
    });
  }
  return bars;
}

/**
 * Compact exposure for an axis or a headline: `6.22 Cr`, `44.09 L Cr`.
 *
 * The wire unit is already crore, so this only groups: `L Cr` at a lakh crore,
 * `K Cr` at a thousand. Values below a crore print in lakh so a quiet strike
 * does not round away to `0.00 Cr`.
 */
export function fmtGex(crore: number): string {
  const abs = Math.abs(crore);
  const sign = crore < 0 ? '-' : '';
  if (abs >= 1e5) return `${sign}${(abs / 1e5).toFixed(2)} L Cr`;
  if (abs >= 1e3) return `${sign}${(abs / 1e3).toFixed(2)} K Cr`;
  if (abs >= 1) return `${sign}${abs.toFixed(2)} Cr`;
  if (abs >= 0.01) return `${sign}${(abs * 100).toFixed(2)} L`;
  return `${sign}0`;
}

/** Same as {@link fmtGex} but always prefixes a `+` on non-negatives. */
export function fmtGexSigned(crore: number): string {
  return (crore >= 0 ? '+' : '') + fmtGex(crore);
}

/** A strike price for a label or a marker chip. */
export function fmtStrike(strike: number): string {
  return strike.toLocaleString('en-IN', { maximumFractionDigits: 2 });
}

/** `11 Aug 2026 (5d)` — the expiry with how long is left on it. */
export function expiryLabel(iso: string | null): string {
  if (!iso) return 'Nearest expiry';
  const date = new Date(iso);
  const days = Math.max(0, Math.round((date.getTime() - Date.now()) / 86_400_000));
  const label = new Intl.DateTimeFormat('en-GB', {
    day: '2-digit',
    month: 'short',
    year: 'numeric'
  }).format(date);
  return `${label} (${days === 0 ? 'today' : `${days}d`})`;
}

/** The four reference levels of one frame, in the order the page reads them. */
export interface GexLevel {
  id: 'callWall' | 'putWall' | 'gammaFlip' | 'netCross';
  label: string;
  /** `null` when this frame's book has no such level. */
  strike: number | null;
  /** Signed distance from spot, in points. `null` follows `strike`. */
  gap: number | null;
  hint: string;
}

export function frameLevels(frame: GexFrame | undefined): GexLevel[] {
  const gap = (strike: number | null) =>
    strike === null || frame === undefined ? null : strike - frame.spot;

  return [
    {
      id: 'callWall',
      label: 'Call Wall',
      strike: frame?.call_wall ?? null,
      gap: gap(frame?.call_wall ?? null),
      hint: 'Heaviest call gamma — dealer hedging tends to cap a rally here.'
    },
    {
      id: 'putWall',
      label: 'Put Wall',
      strike: frame?.put_wall ?? null,
      gap: gap(frame?.put_wall ?? null),
      hint: 'Heaviest put gamma — dealer hedging tends to cushion a fall here.'
    },
    {
      id: 'gammaFlip',
      label: 'Gamma Flip',
      strike: frame?.gamma_flip ?? null,
      gap: gap(frame?.gamma_flip ?? null),
      hint: 'Where the book turns net long gamma. Below it, hedging amplifies moves.'
    },
    {
      id: 'netCross',
      label: 'Net GEX Cross',
      strike: frame?.net_cross ?? null,
      gap: gap(frame?.net_cross ?? null),
      hint: 'Where the per-strike profile changes sign — call interest starts to outweigh put.'
    }
  ];
}

/**
 * The visible window as a spreadsheet.
 *
 * Exports what is on screen, not the whole payload: the strike filter is a
 * deliberate choice about what is worth looking at, and an export that quietly
 * ignored it would not match the chart it was taken from.
 *
 * Pure — it returns the text, and the route owns the Blob. That keeps the
 * escaping testable without a DOM.
 */
export function gexCsv(bars: GexBar[], frame: GexFrame | undefined): string {
  const header = 'strike,call_gex_cr,put_gex_cr,net_gex_cr,abs_gex_cr';
  const rows = bars.map((bar) => [bar.strike, bar.callGex, bar.putGex, bar.net, bar.abs].join(','));
  // A bare table of numbers with no timestamp is unusable a day later, and the
  // scrubbed frame — not "now" — is what these rows describe.
  const stamp = frame ? `# as of ${frame.t}, spot ${frame.spot}` : '# no data';
  return [stamp, header, ...rows].join('\n');
}

/** `gex-NIFTY-2026-08-06-1540.csv` — sortable, and says which frame it is. */
export function csvFilename(symbol: string, frame: GexFrame | undefined): string {
  if (!frame) return `gex-${symbol}.csv`;
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Kolkata',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false
  }).formatToParts(new Date(frame.t));
  const at = (type: string) => parts.find((part) => part.type === type)?.value ?? '00';
  return `gex-${symbol}-${at('year')}-${at('month')}-${at('day')}-${at('hour')}${at('minute')}.csv`;
}
