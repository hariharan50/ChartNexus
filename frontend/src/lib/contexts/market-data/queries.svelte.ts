/**
 * TanStack Query hooks for the market-data REST endpoints.
 *
 * Each hook must be called during component initialisation (they read the
 * QueryClient from context, provided by the terminal layout). A modest
 * `refetchInterval` keeps the dashboard fresh until the websocket stream lands
 * in Phase 2; the query cache it fills is the same cache those live frames will
 * later update, so the page will not need to change again.
 */

import { createQuery } from '@tanstack/svelte-query';
import { toStore } from 'svelte/store';
import {
  getFutures,
  getMarketStatus,
  getOptionChain,
  getSpot
} from '$contexts/broker-connections/api';
import type {
  FuturesQuote,
  MarketStatus,
  OptionChain,
  Quote
} from '$contexts/broker-connections/types';
import { queryKeys } from '$shared/api/query-client';

const REFETCH_MS = 15_000;

export function marketStatusQuery() {
  return createQuery<MarketStatus>({
    queryKey: queryKeys.marketStatus(),
    queryFn: () => getMarketStatus(),
    refetchInterval: REFETCH_MS
  });
}

export function spotQuery(instrument: string) {
  return createQuery<Quote>({
    queryKey: queryKeys.spot(instrument),
    queryFn: () => getSpot(instrument),
    refetchInterval: REFETCH_MS
  });
}

export function futuresQuery(instrument: string) {
  return createQuery<FuturesQuote>({
    queryKey: queryKeys.futures(instrument),
    queryFn: () => getFutures(instrument),
    refetchInterval: REFETCH_MS
  });
}

/**
 * The focused-instrument chain. `instrument` is a getter so switching the index
 * tab re-keys and refetches; `toStore` bridges the rune into the reactive
 * options store `createQuery` expects.
 */
export function optionChainQuery(instrument: () => string) {
  return createQuery<OptionChain>(
    toStore(() => ({
      queryKey: queryKeys.optionChain(instrument(), 'nearest'),
      queryFn: () => getOptionChain(instrument()),
      refetchInterval: REFETCH_MS
    }))
  );
}

/**
 * Like {@link optionChainQuery} but for a chosen expiry. Both arguments are
 * getters so switching the instrument or the expiry re-keys and refetches; a
 * `null`/`undefined` expiry asks the backend for the nearest one.
 */
export function optionChainForExpiryQuery(
  instrument: () => string,
  expiry: () => string | undefined
) {
  return createQuery<OptionChain>(
    toStore(() => ({
      queryKey: queryKeys.optionChain(instrument(), expiry() ?? 'nearest'),
      queryFn: () => getOptionChain(instrument(), expiry()),
      refetchInterval: REFETCH_MS
    }))
  );
}
