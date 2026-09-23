import { apiFetch } from '$shared/api/client';
import type {
  AdvanceDeclineView,
  BreadthSeries,
  SectorRail,
  CashFlowHistory,
  ContributorsView,
  FlowSummary,
  SectorRotationView,
  WeightageView
} from './types';

/** The indices the Analysis pages can be drawn for, in picker order. */
export const INDICES = [
  { id: 'NIFTY50', label: 'NIFTY 50' },
  { id: 'BANKNIFTY', label: 'BANK NIFTY' }
] as const;

export type IndexId = (typeof INDICES)[number]['id'];

export const DEFAULT_INDEX: IndexId = 'NIFTY50';

/**
 * Sessions fetched by the flow pages when nothing else is asked for.
 *
 * A quarter of trading days: long enough for the cumulative line to show a
 * trend, short enough that the daily bars stay individually readable.
 */
export const DEFAULT_SESSIONS = 60;

export function getFiiDiiSummary(
  opts: { sessions?: number; date?: string | null } = {},
  fetcher?: typeof fetch
): Promise<FlowSummary> {
  const params: Record<string, string> = {
    sessions: String(opts.sessions ?? DEFAULT_SESSIONS)
  };
  // Omitted entirely for the latest session, so the server picks it rather
  // than the client guessing a date the exchange may not have published.
  if (opts.date) params.date = opts.date;
  return apiFetch<FlowSummary>({ url: '/breadth/fii-dii/summary', params, fetcher });
}

export function getFiiDiiCash(
  opts: { sessions?: number } = {},
  fetcher?: typeof fetch
): Promise<CashFlowHistory> {
  return apiFetch<CashFlowHistory>({
    url: '/breadth/fii-dii/cash',
    params: { sessions: String(opts.sessions ?? DEFAULT_SESSIONS) },
    fetcher
  });
}

/** Bucket widths the breadth series offers — the backend's own set. */
export const BREADTH_INTERVALS = ['1m', '5m', '15m', '1h'] as const;
export type BreadthInterval = (typeof BREADTH_INTERVALS)[number];
export const DEFAULT_BREADTH_INTERVAL: BreadthInterval = '5m';

export function getBreadthSeries(
  opts: {
    index: string;
    sector?: string | null;
    date?: string | null;
    interval?: BreadthInterval;
  },
  fetcher?: typeof fetch
): Promise<BreadthSeries> {
  const params: Record<string, string> = { index: opts.index };
  // A sector narrows the scope; omitted entirely for the index itself, so the
  // request URL for the default view stays the server's own default.
  if (opts.sector) params.sector = opts.sector;
  if (opts.date) params.date = opts.date;
  if (opts.interval) params.interval = opts.interval;
  return apiFetch<BreadthSeries>({
    url: '/breadth/index/advance-decline/series',
    params,
    fetcher
  });
}

/**
 * The rail: every sector of the F&O universe, with its own names.
 *
 * One read for the whole left column. It carries each sector's members too, so
 * clicking a sector redraws the board beneath the chart without a second
 * request — and without the counts and the rows coming from two different
 * reads of the same board.
 */
export function getSectorRail(fetcher?: typeof fetch): Promise<SectorRail> {
  return apiFetch<SectorRail>({ url: '/breadth/sectors', fetcher });
}

export function getIndexContributors(
  index: string,
  fetcher?: typeof fetch
): Promise<ContributorsView> {
  return apiFetch<ContributorsView>({
    url: '/breadth/index/contributors',
    params: { index },
    fetcher
  });
}

export function getAdvanceDecline(
  index: string,
  fetcher?: typeof fetch
): Promise<AdvanceDeclineView> {
  return apiFetch<AdvanceDeclineView>({
    url: '/breadth/index/advance-decline',
    params: { index },
    fetcher
  });
}

export function getIndexWeightage(index: string, fetcher?: typeof fetch): Promise<WeightageView> {
  return apiFetch<WeightageView>({ url: '/breadth/index/weightage', params: { index }, fetcher });
}

export function getSectorRotation(
  index: string,
  fetcher?: typeof fetch
): Promise<SectorRotationView> {
  return apiFetch<SectorRotationView>({
    url: '/breadth/sector-rotation',
    params: { index },
    fetcher
  });
}
