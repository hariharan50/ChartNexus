import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '$shared/api/query-client';
import { getInstruments } from './api';
import type { Instrument, InstrumentKind, InstrumentList } from './types';

/**
 * The instrument catalog, fetched once and reused everywhere.
 *
 * `staleTime: Infinity` is the point: the universe changes when NSE issues a
 * circular, not between two page views. Every picker, tab strip and dropdown
 * in the terminal reads this one cache entry rather than re-fetching ~220 rows
 * per page.
 */
export function useInstrumentsQuery(opts: { kind?: InstrumentKind; enabled?: boolean } = {}) {
  return useQuery<InstrumentList>({
    queryKey: queryKeys.instruments(opts.kind),
    queryFn: () => getInstruments(opts.kind ? { kind: opts.kind } : {}),
    staleTime: Number.POSITIVE_INFINITY,
    gcTime: Number.POSITIVE_INFINITY,
    // Defaults to on, which is what a page wanting the catalog means. The
    // header search passes `false` until the box is first focused: it is
    // mounted on every terminal page, and most visits never search.
    enabled: opts.enabled ?? true
  });
}

const NONE: Instrument[] = [];

/** Just the rows, so callers do not each unwrap the envelope. */
export function useInstruments(opts: { kind?: InstrumentKind; enabled?: boolean } = {}): {
  instruments: Instrument[];
  isLoading: boolean;
  error: unknown;
} {
  const query = useInstrumentsQuery(opts);
  return {
    instruments: query.data?.instruments ?? NONE,
    isLoading: query.isLoading,
    error: query.error
  };
}
