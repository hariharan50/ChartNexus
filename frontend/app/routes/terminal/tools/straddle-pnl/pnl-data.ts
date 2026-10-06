/**
 * Wire types and pure derivations for the Straddle PnL Simulator.
 *
 * The endpoint ships the whole run in one payload — curve, trade log and
 * summary — so the interval is applied here and switching 1m to 15m costs no
 * round trip. The bucketing helpers are the Options Lab's own rather than a
 * second implementation that rounds its buckets differently at the edges.
 */

import { apiFetch } from '$shared/api/client';

export {
  bucketIndices,
  pick,
  DEFAULT_TIMEFRAME,
  TIMEFRAMES,
  type Timeframe
} from '../../options/atm-straddle/straddle-data';

export { OI_INSTRUMENTS, type Instrument } from '../../options/open-interest/oi-data';

export {
  formatPrice,
  formatPremium,
  formatStrike,
  timeLabel
} from '../straddle-chart/straddle-data';

export interface PnlPoint {
  t: string;
  spot: number;
  atm_strike: number;
  entry_strike: number;
  ce_price: number;
  pe_price: number;
  straddle: number;
  synthetic_future: number;
  pnl: number;
  adjustments: number;
}

export type TradeType = 'ENTRY' | 'ADJUSTMENT' | 'EXIT';

export interface PnlTrade {
  type: TradeType;
  t: string;
  strike: number;
  old_strike: number | null;
  ce_price: number;
  pe_price: number;
  straddle: number;
  exit_ce: number | null;
  exit_pe: number | null;
  exit_straddle: number | null;
  spot: number;
  /** `null` on an ENTRY — the log renders a dash, not a real-looking 0.00. */
  leg_pnl: number | null;
  cumulative_pnl: number;
}

export interface PnlSummary {
  total_pnl: number;
  max_pnl: number;
  min_pnl: number;
  total_adjustments: number;
}

export interface StraddlePnlView {
  instrument_id: string;
  symbol: string;
  expiry_date: string | null;
  lot_size: number;
  lots: number;
  quantity: number;
  adjustment_points: number;
  strike_step: number;
  requested_sessions: number;
  covered_sessions: number;
  open_ts: string;
  now_ts: string;
  spot: number | null;
  entry_strike: number | null;
  data_quality: 'intraday' | 'empty';
  summary: PnlSummary;
  series: PnlPoint[];
  trades: PnlTrade[];
}

/** Everything one run is keyed and fetched by. */
export interface RunParams {
  instrument: string;
  expiry: string | undefined;
  sessions: number;
  adjustmentPoints: number;
  lotSize: number;
  lots: number;
}

export function getStraddlePnl(
  params: RunParams,
  fetcher?: typeof fetch
): Promise<StraddlePnlView> {
  return apiFetch<StraddlePnlView>({
    url: `/options-lab/straddle-pnl/${encodeURIComponent(params.instrument)}`,
    params: {
      sessions: String(params.sessions),
      adjustment_points: String(params.adjustmentPoints),
      lot_size: String(params.lotSize),
      lots: String(params.lots),
      ...(params.expiry ? { expiry: params.expiry } : {})
    },
    fetcher
  });
}

// -- the range --------------------------------------------------------------

/**
 * Sessions, not calendar days — the backend counts stored trading days, so a
 * long weekend cannot quietly turn "3 Days" into one and a half.
 */
export const RANGES: readonly { value: string; label: string; sessions: number }[] = [
  { value: '1', label: '1 Day', sessions: 1 },
  { value: '3', label: '3 Days', sessions: 3 },
  { value: '5', label: '5 Days', sessions: 5 },
  { value: '7', label: '7 Days', sessions: 7 },
  { value: '10', label: '10 Days', sessions: 10 }
];

export const DEFAULT_RANGE = '1';

export function sessionsOf(range: string): number {
  return RANGES.find((entry) => entry.value === range)?.sessions ?? 1;
}

// -- the three lines --------------------------------------------------------

export const PNL = 'P&L';
export const SPOT = 'Spot';
export const SYNTHETIC = 'Synthetic Fut';

/**
 * The P&L curve's two colours, switched at zero.
 *
 * Deliberately not the call-green / put-red pair from the Open Interest page:
 * these mean "making money" and "losing money", and reusing the contract
 * colours would have a green stretch read as call-side.
 */
export const PNL_POSITIVE = '#4ade80';
export const PNL_NEGATIVE = '#f87171';
export const SPOT_COLOR = '#e2e8f0';
export const SYNTHETIC_COLOR = '#60a5fa';

// -- the exchanges ----------------------------------------------------------

/**
 * Which exchange each index's options list on. Fixed rather than a picker: the
 * archive holds exactly these three, so an exchange control would be a dropdown
 * whose every other choice returns nothing.
 */
export const EXCHANGE_OF: Readonly<Record<string, string>> = {
  NIFTY: 'NFO',
  BANKNIFTY: 'NFO',
  SENSEX: 'BFO'
};

export function exchangeOf(symbol: string): string {
  return EXCHANGE_OF[symbol] ?? 'NFO';
}

// -- formatting -------------------------------------------------------------

/** `-2,548.00` — thousands separated, always two places, for money columns. */
export function formatMoney(value: number): string {
  return value.toLocaleString('en-IN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  });
}

/** `05 Oct 09:15` in IST — 24-hour, because 13:18 is not PM. */
export function tradeTime(iso: string): string {
  const at = Date.parse(iso);
  if (Number.isNaN(at)) return iso;
  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Asia/Kolkata',
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false
  }).formatToParts(new Date(at));
  const take = (type: string) => parts.find((part) => part.type === type)?.value ?? '';
  return `${take('day')} ${take('month')} ${take('hour')}:${take('minute')}`;
}

/** The strike column: `22550`, or `22550 → 22500` on an adjustment. */
export function strikeLabel(trade: PnlTrade): string {
  const held = formatStrikeValue(trade.strike);
  return trade.old_strike == null ? held : `${formatStrikeValue(trade.old_strike)} → ${held}`;
}

function formatStrikeValue(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

/** `pos`, `neg` or `flat` — the sign a money cell should be painted by. */
export function signOf(value: number | null): 'pos' | 'neg' | 'flat' {
  if (value == null || value === 0) return 'flat';
  return value > 0 ? 'pos' : 'neg';
}

/**
 * What the run can honestly say about the window it replayed.
 *
 * A request for five sessions answered with two is not an error — the archive
 * accrues forward and is pruned — but a curve that silently replayed two under
 * a "5 Days" control would read as a strategy that simply did nothing.
 */
export function coverageNote(view: StraddlePnlView | undefined): string | null {
  if (!view) return null;
  if (view.data_quality === 'empty') {
    return 'No captures for this window — the archive is written by the ingest worker, and a simulation needs a session to replay.';
  }
  if (view.covered_sessions < view.requested_sessions) {
    return `${view.covered_sessions} of ${view.requested_sessions} sessions are in the archive; the run replays what exists.`;
  }
  return null;
}
