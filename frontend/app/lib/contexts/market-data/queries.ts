/**
 * TanStack Query hooks for the market-data REST endpoints.
 *
 * Each hook reads the QueryClient from context, provided by the terminal
 * layout. A modest `refetchInterval` keeps the dashboard fresh until the
 * websocket stream lands; the query cache it fills is the same cache those live
 * frames will later update, so the page will not need to change again.
 *
 * Svelte needed `toStore(() => …)` to make a changing instrument re-key the
 * query. React re-evaluates the options object on every render, so the getter
 * parameters collapse to plain values.
 */

import { useQuery } from '@tanstack/react-query';
import {
  getExpiries,
  getFutures,
  getMarketStatus,
  getOptionChain,
  getSpot
} from '$contexts/broker-connections/api';
import type {
  ExpiryList,
  FuturesQuote,
  MarketStatus,
  OptionChain,
  Quote
} from '$contexts/broker-connections/types';
import { queryKeys } from '$shared/api/query-client';

const REFETCH_MS = 15_000;

export function useMarketStatusQuery() {
  return useQuery<MarketStatus>({
    queryKey: queryKeys.marketStatus(),
    queryFn: () => getMarketStatus(),
    refetchInterval: REFETCH_MS
  });
}

export function useSpotQuery(instrument: string) {
  return useQuery<Quote>({
    queryKey: queryKeys.spot(instrument),
    queryFn: () => getSpot(instrument),
    refetchInterval: REFETCH_MS
  });
}

export function useFuturesQuery(instrument: string) {
  return useQuery<FuturesQuote>({
    queryKey: queryKeys.futures(instrument),
    queryFn: () => getFutures(instrument),
    refetchInterval: REFETCH_MS
  });
}

/** The focused-instrument chain; switching the index tab re-keys and refetches. */
export function useOptionChainQuery(instrument: string) {
  return useQuery<OptionChain>({
    queryKey: queryKeys.optionChain(instrument, 'nearest'),
    queryFn: () => getOptionChain(instrument),
    refetchInterval: REFETCH_MS
  });
}

/**
 * Like {@link useOptionChainQuery} but for a chosen expiry. An
 * `undefined` expiry asks the backend for the nearest one.
 */
export function useOptionChainForExpiryQuery(instrument: string, expiry: string | undefined) {
  return useQuery<OptionChain>({
    queryKey: queryKeys.optionChain(instrument, expiry ?? 'nearest'),
    queryFn: () => getOptionChain(instrument, expiry),
    refetchInterval: REFETCH_MS
  });
}

/**
 * The instrument's listed expiries, for the Options Lab expiry picker.
 *
 * Refetched rarely on purpose: the listed expiries change when a contract
 * settles, which is once a week - polling them on the terminal's fifteen-second
 * loop would spend a broker request a minute on a list that is stable for days.
 */
export function useExpiriesQuery(instrument: string) {
  return useQuery<ExpiryList>({
    queryKey: ['market', 'expiries', instrument],
    queryFn: () => getExpiries(instrument),
    staleTime: 15 * 60_000,
    refetchInterval: 30 * 60_000
  });
}
