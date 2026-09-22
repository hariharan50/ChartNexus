import { useQuery } from '@tanstack/react-query';
import {
  DEFAULT_SESSIONS,
  getAdvanceDecline,
  getFiiDiiCash,
  getFiiDiiSummary,
  getIndexContributors,
  getIndexWeightage,
  getSectorRotation
} from './api';
import type {
  AdvanceDeclineView,
  CashFlowHistory,
  ContributorsView,
  FlowSummary,
  SectorRotationView,
  WeightageView
} from './types';

/**
 * The four index reads share one board fetch on the server, so they are polled
 * at the same cadence as the rest of the terminal — every refresh costs the
 * shared broker request quota.
 */
const INDEX_REFETCH_MS = 15_000;

/**
 * The participant file is published once, after the close. Polling it on a
 * fifteen-second loop would re-fetch the same rows four times a minute for a
 * number that changes at most once a day.
 */
const FLOW_REFETCH_MS = 5 * 60_000;

export function useFiiDiiSummaryQuery(opts: { sessions?: number; date?: string | null } = {}) {
  const sessions = opts.sessions ?? DEFAULT_SESSIONS;
  const date = opts.date ?? null;
  return useQuery<FlowSummary>({
    queryKey: ['breadth', 'fii-dii', 'summary', sessions, date],
    queryFn: () => getFiiDiiSummary({ sessions, date }),
    // An archived session cannot change, so only the live view polls. This
    // also keeps date-stepping from re-fetching a settled day on a timer.
    refetchInterval: date === null ? FLOW_REFETCH_MS : false,
    // Keeps the previous day on screen while the next one loads, so stepping
    // through sessions does not flash the whole page back to a spinner.
    placeholderData: (previous) => previous
  });
}

export function useFiiDiiCashQuery(opts: { sessions?: number } = {}) {
  const sessions = opts.sessions ?? DEFAULT_SESSIONS;
  return useQuery<CashFlowHistory>({
    queryKey: ['breadth', 'fii-dii', 'cash', sessions],
    queryFn: () => getFiiDiiCash({ sessions }),
    refetchInterval: FLOW_REFETCH_MS
  });
}

export function useIndexContributorsQuery(index: string) {
  return useQuery<ContributorsView>({
    queryKey: ['breadth', 'contributors', index],
    queryFn: () => getIndexContributors(index),
    refetchInterval: INDEX_REFETCH_MS
  });
}

export function useAdvanceDeclineQuery(index: string) {
  return useQuery<AdvanceDeclineView>({
    queryKey: ['breadth', 'advance-decline', index],
    queryFn: () => getAdvanceDecline(index),
    refetchInterval: INDEX_REFETCH_MS
  });
}

export function useIndexWeightageQuery(index: string) {
  return useQuery<WeightageView>({
    queryKey: ['breadth', 'weightage', index],
    queryFn: () => getIndexWeightage(index),
    refetchInterval: INDEX_REFETCH_MS
  });
}

export function useSectorRotationQuery(index: string) {
  return useQuery<SectorRotationView>({
    queryKey: ['breadth', 'sector-rotation', index],
    queryFn: () => getSectorRotation(index),
    refetchInterval: INDEX_REFETCH_MS
  });
}
