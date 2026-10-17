import { useQuery } from '@tanstack/react-query';
import { inPreOpenWatch } from '$contexts/market-data/gap-forecast';
import { getGlobalView } from './api';
import type { GlobalView } from './types';

/**
 * Polled on the data's own cadence, the way the breadth queries are.
 *
 * A minute while something is trading somewhere; five minutes when the whole
 * world is shut. The server caches closed markets for half an hour anyway, so
 * a faster client poll would only re-read its own cache.
 *
 * The third rate is the morning one. Between 08:00 and the bell this response
 * is not background colour on a page someone is browsing — it is the number the
 * dashboard's gap card is forecasting the open from, with GIFT repricing all
 * the way to 09:15. A minute-old estimate in that window is a minute-old
 * estimate of something that moves.
 */
const ACTIVE_REFETCH_MS = 60_000;
const QUIET_REFETCH_MS = 5 * 60_000;
const PRE_OPEN_REFETCH_MS = 30_000;

export const GLOBAL_VIEW_KEY = ['global', 'view'] as const;

interface Options {
  /**
   * Off while nothing on screen reads it. The dashboard's gap card needs this
   * response only until the opening print lands, and a page polling a
   * nine-market board it has stopped rendering is quota spent on nothing.
   */
  enabled?: boolean;
}

export function useGlobalViewQuery({ enabled = true }: Options = {}) {
  return useQuery<GlobalView>({
    queryKey: GLOBAL_VIEW_KEY,
    queryFn: () => getGlobalView(),
    enabled,
    refetchInterval: (query) => {
      if (inPreOpenWatch()) return PRE_OPEN_REFETCH_MS;
      const bands = query.state.data?.bands ?? [];
      return bands.some((band) => band.state === 'live') ? ACTIVE_REFETCH_MS : QUIET_REFETCH_MS;
    },
    // Keeps the last good board on screen through a refetch, so the page does
    // not flash back to skeletons every minute.
    placeholderData: (previous) => previous
  });
}
