/**
 * Wire types and pure derivations for the Straddle Chart tool.
 *
 * The endpoint ships the whole window in one payload, so the interval is
 * applied here — switching 1m to 15m is instant rather than a round trip. The
 * bucketing helpers are the Options Lab's own rather than a second
 * implementation that rounds its buckets differently at the edges.
 */

import { apiFetch } from '$shared/api/client';
import { seriesColor } from '$shared/charts/options/multi-series';
import type { ChartTheme } from '$shared/charts/theme/types';

export {
  bucketIndices,
  pick,
  DEFAULT_TIMEFRAME,
  TIMEFRAMES,
  type Timeframe
} from '../../options/atm-straddle/straddle-data';

export { OI_INSTRUMENTS, REFETCH_MS, type Instrument } from '../../options/open-interest/oi-data';

export interface StraddleSeries {
  t: string[];
  strike: number[];
  ce: (number | null)[];
  pe: (number | null)[];
  straddle: number[];
  spot: (number | null)[];
  synthetic: (number | null)[];
}

export interface StraddleChartView {
  instrument_id: string;
  symbol: string;
  expiry_date: string | null;
  lot_size: number | null;
  straddle_price: number | null;
  atm_strike: number | null;
  ce_ltp: number | null;
  pe_ltp: number | null;
  spot: number | null;
  synthetic_future: number | null;
  requested_sessions: number;
  covered_sessions: number;
  open_ts: string;
  now_ts: string;
  data_quality: 'intraday' | 'live' | 'empty';
  rolling_strike: boolean;
  series: StraddleSeries;
}

export function getStraddleChart(
  instrument: string,
  opts: {
    sessions?: number | undefined;
    expiry?: string | undefined;
    date?: string | undefined;
  } = {},
  fetcher?: typeof fetch
): Promise<StraddleChartView> {
  return apiFetch<StraddleChartView>({
    url: `/options-lab/straddle-chart/${encodeURIComponent(instrument)}`,
    params: {
      ...(opts.sessions ? { sessions: String(opts.sessions) } : {}),
      ...(opts.expiry ? { expiry: opts.expiry } : {}),
      ...(opts.date ? { date: opts.date } : {})
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
  { value: '10', label: '10 Days', sessions: 10 }
];

export const DEFAULT_RANGE = '1';

// -- the three lines --------------------------------------------------------

export const STRADDLE = 'Straddle';
export const SPOT = 'Spot';
export const SYNTHETIC = 'Synthetic Fut';

/**
 * Colours for the two coloured lines, from the shared contract palette the
 * Options Lab charts assign by position — so a chip here means the same kind of
 * thing it means on MultiStrike. Spot has none: it plots in the price-reference
 * slot, which the chart draws dashed in the axis colour.
 */
export function straddleColors(_theme: ChartTheme): Record<string, string> {
  return {
    [STRADDLE]: seriesColor(0),
    [SYNTHETIC]: seriesColor(1)
  };
}

export function sessionsOf(range: string): number {
  return RANGES.find((entry) => entry.value === range)?.sessions ?? 1;
}

// -- formatting -------------------------------------------------------------

export function formatPremium(value: number): string {
  return value.toFixed(2);
}

export function formatPrice(value: number): string {
  return value.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function formatStrike(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

/** `11:30`, or `30/09 11:30` once the window spans more than one session. */
export function timeLabel(iso: string, withDay: boolean): string {
  const at = Date.parse(iso);
  if (Number.isNaN(at)) return iso;
  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Asia/Kolkata',
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false
  }).formatToParts(new Date(at));
  const take = (type: string) => parts.find((part) => part.type === type)?.value ?? '';
  const clock = `${take('hour')}:${take('minute')}`;
  return withDay ? `${take('day')}/${take('month')} ${clock}` : clock;
}

/**
 * What the chart can honestly say about the window it drew.
 *
 * A request for five sessions that came back with two is not an error — the
 * archive accrues forward and is pruned — but a chart that silently drew two
 * under a "5 Days" control would read as a market that stood still.
 */
export function coverageNote(view: StraddleChartView | undefined): string | null {
  if (!view) return null;
  if (view.data_quality === 'empty') {
    return 'No captures for this window — the archive is written by the ingest worker.';
  }
  if (view.data_quality === 'live') {
    return 'One live reading: nothing was archived for this window, so there is no history to draw.';
  }
  if (view.covered_sessions < view.requested_sessions) {
    return `${view.covered_sessions} of ${view.requested_sessions} sessions are in the archive; the chart draws what exists.`;
  }
  return null;
}
