import { apiFetch } from '$shared/api/client';
import type {
  AdvanceDeclineView,
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
