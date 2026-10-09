import { QueryClient } from '@tanstack/react-query';
import { describe, expect, it } from 'vitest';
import { queryKeys } from '../../app/lib/shared/api/query-client';
import type { SnapshotPayload } from '../../app/lib/shared/realtime/protocol';
import { invalidateForSnapshot } from '../../app/lib/shared/realtime/query-cache-sync';

/**
 * What a frame actually refetches.
 *
 * Asserted against a real QueryClient rather than a spy, because the thing
 * worth pinning is the *matching* — whether `['option-chain', 'NIFTY']` reaches
 * every expiry of NIFTY and no expiry of BANKNIFTY. A spy would only prove the
 * call was made with the argument we chose.
 *
 * Over-invalidating is the failure mode with a bill attached: each stale query
 * the pages are watching becomes a refetch, and a refetch is a broker request
 * against a 100k/day quota.
 */

function payload(symbol: string): SnapshotPayload {
  return {
    symbol,
    session_date: '2026-10-09',
    captured_at: '2026-10-09T08:30:00Z',
    source: 'mock',
    spot: '24512.35',
    expiry: '2026-10-14'
  };
}

/**
 * A client seeded with fresh entries for two symbols.
 *
 * `staleTime: Infinity` is what makes the assertions meaningful: nothing goes
 * stale on its own, so a stale entry afterwards was invalidated by the code
 * under test and by nothing else.
 */
function seeded(): QueryClient {
  const client = new QueryClient({
    defaultOptions: { queries: { staleTime: Infinity, retry: false } }
  });

  for (const symbol of ['NIFTY', 'BANKNIFTY']) {
    client.setQueryData(queryKeys.spot(symbol), { price: '1' });
    client.setQueryData(queryKeys.futures(symbol), { price: '1' });
    client.setQueryData(queryKeys.dashboard(symbol), { ok: true });
    client.setQueryData(queryKeys.optionChain(symbol, 'nearest'), { rows: [] });
    client.setQueryData(queryKeys.optionChain(symbol, '2026-10-21'), { rows: [] });
    client.setQueryData(queryKeys.optionMetrics(symbol, 'nearest', 'pcr'), { value: 1 });
    client.setQueryData(['market', 'expiries', symbol], { expiries: [] });
  }
  client.setQueryData(queryKeys.marketStatus(), { phase: 'open' });
  client.setQueryData(queryKeys.instruments(), { instruments: [] });

  return client;
}

const isStale = (client: QueryClient, key: readonly unknown[]): boolean =>
  client.getQueryState(key as unknown[])?.isInvalidated === true;

describe('invalidateForSnapshot', () => {
  it('stales the moved symbol’s spot, futures and dashboard', () => {
    const client = seeded();

    invalidateForSnapshot(client, payload('NIFTY'));

    expect(isStale(client, queryKeys.spot('NIFTY'))).toBe(true);
    expect(isStale(client, queryKeys.futures('NIFTY'))).toBe(true);
    expect(isStale(client, queryKeys.dashboard('NIFTY'))).toBe(true);
  });

  it('stales every expiry of that symbol’s chain', () => {
    // The event does not say which expiry was written, so all of them go.
    const client = seeded();

    invalidateForSnapshot(client, payload('NIFTY'));

    expect(isStale(client, queryKeys.optionChain('NIFTY', 'nearest'))).toBe(true);
    expect(isStale(client, queryKeys.optionChain('NIFTY', '2026-10-21'))).toBe(true);
  });

  it('stales that symbol’s option metrics', () => {
    const client = seeded();

    invalidateForSnapshot(client, payload('NIFTY'));

    expect(isStale(client, queryKeys.optionMetrics('NIFTY', 'nearest', 'pcr'))).toBe(true);
  });

  it('stales market status, which a written snapshot is evidence about', () => {
    const client = seeded();

    invalidateForSnapshot(client, payload('NIFTY'));

    expect(isStale(client, queryKeys.marketStatus())).toBe(true);
  });

  it('leaves every other symbol alone', () => {
    // The prefix match must not leak across symbols.
    const client = seeded();

    invalidateForSnapshot(client, payload('NIFTY'));

    expect(isStale(client, queryKeys.spot('BANKNIFTY'))).toBe(false);
    expect(isStale(client, queryKeys.futures('BANKNIFTY'))).toBe(false);
    expect(isStale(client, queryKeys.dashboard('BANKNIFTY'))).toBe(false);
    expect(isStale(client, queryKeys.optionChain('BANKNIFTY', 'nearest'))).toBe(false);
    expect(isStale(client, queryKeys.optionMetrics('BANKNIFTY', 'nearest', 'pcr'))).toBe(false);
  });

  it('does not touch the instrument catalog', () => {
    // Refreshed daily from the exchange symbol master; a snapshot says nothing
    // about the universe, and refetching it would spend a broker request.
    const client = seeded();

    invalidateForSnapshot(client, payload('NIFTY'));

    expect(isStale(client, queryKeys.instruments())).toBe(false);
  });

  it('does not touch the expiry lists', () => {
    // They change when a contract settles — once a week. Invalidating them on
    // every snapshot would spend a broker request a minute on a stable list.
    const client = seeded();

    invalidateForSnapshot(client, payload('NIFTY'));

    expect(isStale(client, ['market', 'expiries', 'NIFTY'])).toBe(false);
  });

  it('a prefix symbol is not a match', () => {
    // NIFTYNXT50 moving must not stale NIFTY's chain, and vice versa.
    const client = new QueryClient({
      defaultOptions: { queries: { staleTime: Infinity, retry: false } }
    });
    client.setQueryData(queryKeys.optionChain('NIFTY', 'nearest'), { rows: [] });
    client.setQueryData(queryKeys.optionChain('NIFTYNXT50', 'nearest'), { rows: [] });

    invalidateForSnapshot(client, payload('NIFTYNXT50'));

    expect(isStale(client, queryKeys.optionChain('NIFTYNXT50', 'nearest'))).toBe(true);
    expect(isStale(client, queryKeys.optionChain('NIFTY', 'nearest'))).toBe(false);
  });
});
