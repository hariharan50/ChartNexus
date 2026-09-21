import { apiFetch } from '$shared/api/client';
import type { InstrumentKind, InstrumentList } from './types';

/**
 * The tradeable universe.
 *
 * Deliberately one unpaged call: it is ~220 rows, it backs a picker that has
 * to filter instantly, and the response is cached for the session.
 */
export function getInstruments(
  opts: { kind?: InstrumentKind; search?: string } = {},
  fetcher?: typeof fetch
): Promise<InstrumentList> {
  const params: Record<string, string> = {};
  if (opts.kind) params.kind = opts.kind;
  if (opts.search) params.search = opts.search;
  return apiFetch<InstrumentList>({ url: '/instruments', params, fetcher });
}
