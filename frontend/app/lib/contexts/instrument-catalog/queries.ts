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
export function useInstrumentsQuery(opts: { kind?: InstrumentKind } = {}) {
  return useQuery<InstrumentList>({
    queryKey: queryKeys.instruments(opts.kind),
    queryFn: () => getInstruments(opts.kind ? { kind: opts.kind } : {}),
    staleTime: Number.POSITIVE_INFINITY,
    gcTime: Number.POSITIVE_INFINITY
  });
}

const NONE: Instrument[] = [];

/** Just the rows, so callers do not each unwrap the envelope. */
export function useInstruments(opts: { kind?: InstrumentKind } = {}): {
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
