/**
 * Turning a frame into cache invalidation.
 *
 * This is what `queryKeys` in `query-client.ts` was centralised for — "so
 * realtime updates can invalidate exactly the right slice of cache without
 * guessing at key shapes".
 *
 * The socket never carries data into the cache, only the news that the cache is
 * stale. The frame is a prompt; TanStack Query then refetches through the same
 * REST hooks the pages already use, so a live update and a polled one produce
 * byte-identical state and no page needs to know which it got.
 *
 * **Invalidating too widely is the real cost here.** Every key below is scoped
 * to the one symbol that moved. The instrument catalog and the expiry lists are
 * deliberately left alone: they change daily and weekly, each refetch spends a
 * broker request against a 100k/day quota, and a snapshot says nothing about
 * either.
 */

import type { QueryClient } from '@tanstack/react-query';
import { queryKeys } from '$shared/api/query-client';
import type { SnapshotPayload } from './protocol';

/**
 * Mark everything a new option-chain snapshot makes stale, for one symbol.
 *
 * Partial keys are used where a query is keyed more finely than the event is.
 * `queryKeys.optionChain(symbol, expiry)` is `['option-chain', symbol, expiry]`,
 * and a snapshot can be for any expiry, so the prefix `['option-chain', symbol]`
 * invalidates every expiry of that symbol and nothing of any other.
 */
export function invalidateForSnapshot(client: QueryClient, payload: SnapshotPayload): void {
  const { symbol } = payload;

  // Exact keys: one entry each.
  void client.invalidateQueries({ queryKey: queryKeys.spot(symbol) });
  void client.invalidateQueries({ queryKey: queryKeys.futures(symbol) });
  void client.invalidateQueries({ queryKey: queryKeys.dashboard(symbol) });

  // Prefixes: every expiry, and every metric within it.
  void client.invalidateQueries({ queryKey: ['option-chain', symbol] });
  void client.invalidateQueries({ queryKey: ['option-metrics', symbol] });

  // Market status is not per-symbol, but a snapshot having been written is
  // itself evidence about the session — the archive only grows while the market
  // is open, so a frame arriving is the earliest signal that an "closed" badge
  // is out of date.
  void client.invalidateQueries({ queryKey: queryKeys.marketStatus() });
}

/**
 * The queries a snapshot for `symbol` touches, as predicates.
 *
 * Exported for the test, and as the honest answer to "what does a frame
 * actually refetch?" — a question worth being able to answer exactly, since
 * every entry costs a request.
 */
export function invalidatedKeysFor(symbol: string): readonly unknown[][] {
  return [
    queryKeys.spot(symbol) as unknown as unknown[],
    queryKeys.futures(symbol) as unknown as unknown[],
    queryKeys.dashboard(symbol) as unknown as unknown[],
    ['option-chain', symbol],
    ['option-metrics', symbol],
    queryKeys.marketStatus() as unknown as unknown[]
  ];
}
