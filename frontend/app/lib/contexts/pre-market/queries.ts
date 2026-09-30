import { useQuery } from '@tanstack/react-query';
import { getPreMarketView } from './api';
import type { PreMarketView } from './types';

/**
 * Polled on the session's own cadence.
 *
 * Faster before the open than after it: the half hour to 09:15 is when GIFT,
 * the global board and the chain are all still moving and the reader is
 * actually deciding something. Once the market is open this stops being the
 * page you watch, and once it has closed almost nothing on it can change.
 */
const PRE_OPEN_REFETCH_MS = 30_000;
const SESSION_REFETCH_MS = 60_000;
const CLOSED_REFETCH_MS = 5 * 60_000;

export const PRE_MARKET_VIEW_KEY = ['pre-market', 'view'] as const;

export function usePreMarketViewQuery(focus: string) {
  return useQuery<PreMarketView>({
    queryKey: [...PRE_MARKET_VIEW_KEY, focus],
    queryFn: () => getPreMarketView(focus),
    refetchInterval: (query) => {
      const phase = query.state.data?.phase;
      if (!phase) return PRE_OPEN_REFETCH_MS;
      if (phase.is_open) return SESSION_REFETCH_MS;
      // Both sides of the session are "closed"; only the pre-open half is
      // worth polling hard, and the clock is the only thing that tells them
      // apart.
      return phase.time_ist < phase.opens_ist ? PRE_OPEN_REFETCH_MS : CLOSED_REFETCH_MS;
    },
    // Keeps the last good read on screen through a refetch, so the page does
    // not flash back to skeletons every half minute.
    placeholderData: (previous) => previous
  });
}
