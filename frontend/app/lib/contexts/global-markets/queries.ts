import { useQuery } from '@tanstack/react-query';
import { getGlobalView } from './api';
import type { GlobalView } from './types';

/**
 * Polled on the data's own cadence, the way the breadth queries are.
 *
 * A minute while something is trading somewhere; five minutes when the whole
 * world is shut. The server caches closed markets for half an hour anyway, so
 * a faster client poll would only re-read its own cache.
 */
const ACTIVE_REFETCH_MS = 60_000;
const QUIET_REFETCH_MS = 5 * 60_000;

export const GLOBAL_VIEW_KEY = ['global', 'view'] as const;

export function useGlobalViewQuery() {
  return useQuery<GlobalView>({
    queryKey: GLOBAL_VIEW_KEY,
    queryFn: () => getGlobalView(),
    refetchInterval: (query) => {
      const bands = query.state.data?.bands ?? [];
      return bands.some((band) => band.state === 'live') ? ACTIVE_REFETCH_MS : QUIET_REFETCH_MS;
    },
    // Keeps the last good board on screen through a refetch, so the page does
    // not flash back to skeletons every minute.
    placeholderData: (previous) => previous
  });
}
