import { useQuery } from '@tanstack/react-query';
import { getFuturesBoard, getFuturesDashboard } from './api';
import type { FuturesBoard, FuturesDashboard } from './types';

/**
 * The board is one broker read across the whole universe, so it is polled at
 * the same cadence as the rest of the terminal rather than anything faster —
 * every refresh costs the shared request quota.
 */
const REFETCH_MS = 15_000;

export function useFuturesDashboardQuery(opts: { limit?: number; sector?: string } = {}) {
  return useQuery<FuturesDashboard>({
    queryKey: ['futures', 'dashboard', opts.limit ?? null, opts.sector ?? null],
    queryFn: () => getFuturesDashboard(opts),
    refetchInterval: REFETCH_MS
  });
}

export function useFuturesBoardQuery(
  opts: { sector?: string; kind?: 'index' | 'stock' } = {},
  options: { refetchInterval?: number } = {}
) {
  return useQuery<FuturesBoard>({
    queryKey: ['futures', 'board', opts.sector ?? null, opts.kind ?? null],
    queryFn: () => getFuturesBoard(opts),
    refetchInterval: options.refetchInterval ?? REFETCH_MS
  });
}
