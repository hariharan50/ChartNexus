import { useQuery } from '@tanstack/react-query';
import { getFuturesBoard, getFuturesDashboard, getFuturesExpiries } from './api';
import type { ExpiryList, FuturesBoard, FuturesDashboard } from './types';

/**
 * The board is one broker read across the whole universe, so it is polled at
 * the same cadence as the rest of the terminal rather than anything faster —
 * every refresh costs the shared request quota.
 */
const REFETCH_MS = 15_000;

/**
 * Which contracts the exchange lists changes once a day, at most, so this is
 * fetched once and shared by every page that shows the picker rather than
 * polled alongside the board.
 */
const EXPIRIES_STALE_MS = 30 * 60_000;

export function useFuturesDashboardQuery(
  opts: { limit?: number; sector?: string; series?: number } = {}
) {
  return useQuery<FuturesDashboard>({
    // `series` is part of the key, not a refetch trigger on one key: two
    // series are two different boards, and sharing a cache entry would flash
    // the near month's rows under the next month's heading while it loads.
    queryKey: ['futures', 'dashboard', opts.limit ?? null, opts.sector ?? null, opts.series ?? 0],
    queryFn: () => getFuturesDashboard(opts),
    refetchInterval: REFETCH_MS
  });
}

export function useFuturesBoardQuery(
  opts: { sector?: string; kind?: 'index' | 'stock'; series?: number } = {},
  options: { refetchInterval?: number } = {}
) {
  return useQuery<FuturesBoard>({
    queryKey: ['futures', 'board', opts.sector ?? null, opts.kind ?? null, opts.series ?? 0],
    queryFn: () => getFuturesBoard(opts),
    refetchInterval: options.refetchInterval ?? REFETCH_MS
  });
}

export function useFuturesExpiriesQuery() {
  return useQuery<ExpiryList>({
    queryKey: ['futures', 'expiries'],
    queryFn: () => getFuturesExpiries(),
    staleTime: EXPIRIES_STALE_MS
  });
}
