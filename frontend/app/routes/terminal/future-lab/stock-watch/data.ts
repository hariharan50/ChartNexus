/**
 * Everything Stock Watch reads, and where it reads it from.
 *
 * **No new endpoints.** The terminal already serves every figure this page
 * needs, under the app's own `/market`, `/futures` and `/instruments` prefixes.
 * The spec this page was built to proposed a parallel `/api/v1/stocks/*` tree;
 * standing that up would have given the same numbers two URLs, two caches and
 * two chances to disagree on screen. The mapping is recorded here instead, so
 * the next reader can see the decision rather than wonder about it:
 *
 * | Asked for                   | Served by                                |
 * | --------------------------- | ---------------------------------------- |
 * | `stocks/search`             | `GET /instruments` (one cached catalog)   |
 * | `stocks/{s}/overview`       | `GET /market/spot` + `/market/status`     |
 * | `stocks/{s}/candles`        | `GET /market/history`                     |
 * | `stocks/{s}/levels`         | computed from candles in `calc/levels`    |
 * | `stocks/{s}/futures`        | `GET /market/futures` + `GET /futures/board` |
 * | `stocks/{s}/option-expiries`| `GET /market/expiries`                    |
 * | `stocks/{s}/option-chain`   | `GET /market/option-chain`                |
 * | `stocks/{s}/oi-analytics`   | computed from the chain in `calc/analytics` |
 * | `stocks/{s}/volatility`     | same, plus history for realised vol       |
 * | `analysis/*`                | computed in `calc/plan`, client-side      |
 * | `analysis/ai-report`        | `POST /copilot/{s}/ask`                   |
 * | `market-data/status`        | `GET /market/status`                      |
 *
 * `stocks/{s}/events` has no row because nothing serves it. There is no
 * corporate-actions provider wired into this application, so the events panel
 * renders an unavailable state rather than a plausible-looking list. See
 * `EventsPanel`.
 *
 * **Everything is keyed by symbol** and shares the terminal's existing query
 * keys, so a chain already fetched by the Options Lab is not fetched again
 * here — and cannot show a different book.
 */

import { useQuery } from '@tanstack/react-query';
import { getExpiries, getFutures, getOptionChain, getSpot } from '$contexts/broker-connections/api';
import type {
  ExpiryList,
  FuturesQuote,
  OptionChain,
  Quote
} from '$contexts/broker-connections/types';
import { useFuturesBoardQuery } from '$contexts/futures-analytics/queries';
import type { FuturesBoard, FuturesRow } from '$contexts/futures-analytics/types';
import { queryKeys } from '$shared/api/query-client';
import { getHistory, type HistoryView, type Interval } from '../../analyse/analyse-data';

/** The terminal's own cadence. Faster would spend broker quota, not gain information. */
const REFETCH_MS = 15_000;
/** Expiries change when a contract settles. Polling them per tick is waste. */
const SLOW_REFETCH_MS = 30 * 60_000;

export function useStockSpotQuery(symbol: string) {
  return useQuery<Quote>({
    queryKey: queryKeys.spot(symbol),
    queryFn: () => getSpot(symbol),
    refetchInterval: REFETCH_MS,
    placeholderData: (previous) => previous
  });
}

export function useStockFuturesQuery(symbol: string) {
  return useQuery<FuturesQuote>({
    queryKey: queryKeys.futures(symbol),
    queryFn: () => getFutures(symbol),
    refetchInterval: REFETCH_MS,
    placeholderData: (previous) => previous
  });
}

export function useStockExpiriesQuery(symbol: string) {
  return useQuery<ExpiryList>({
    queryKey: ['market', 'expiries', symbol],
    queryFn: () => getExpiries(symbol),
    staleTime: 15 * 60_000,
    refetchInterval: SLOW_REFETCH_MS
  });
}

/**
 * The chain for one expiry.
 *
 * `placeholderData` keeps the previous book on screen through a refetch, so
 * the table does not blink to skeletons every fifteen seconds. It is *not*
 * kept across an expiry change: those are different contracts, and showing
 * July's rows under an August header for one frame is the kind of thing a
 * reader screenshots.
 */
export function useStockChainQuery(symbol: string, expiry: string | undefined) {
  return useQuery<OptionChain>({
    queryKey: queryKeys.optionChain(symbol, expiry ?? 'nearest'),
    queryFn: () => getOptionChain(symbol, expiry),
    refetchInterval: REFETCH_MS,
    placeholderData: (previous, previousQuery) => {
      const key = previousQuery?.queryKey as readonly unknown[] | undefined;
      return key?.[2] === (expiry ?? 'nearest') ? previous : undefined;
    }
  });
}

/**
 * Price bars, `live_only` — the same contract the Analyse chart uses.
 *
 * Synthetic candles are indistinguishable from traded ones once drawn, and
 * every level this page derives comes off these bars. An empty series stamped
 * `unavailable` is the honest answer and the chart says so.
 */
export function useStockHistoryQuery(symbol: string, interval: Interval, days: number) {
  return useQuery<HistoryView>({
    queryKey: ['market', 'history', symbol, interval, days],
    queryFn: () => getHistory(symbol, interval, days),
    refetchInterval: REFETCH_MS,
    placeholderData: (previous) => previous
  });
}

// -- futures board ------------------------------------------------------------

/**
 * The classified futures board, for this stock's open interest and build-up.
 *
 * `/market/futures` gives the contract's price and volume but no open
 * interest; the board carries OI, its change and the 2x2 classification for
 * every contract in one pass. The whole board rather than one row because that
 * is the endpoint that exists — and it is already the cache the Future
 * Dashboard and Market Movers fill, so on a terminal where either has been
 * open this costs nothing and cannot disagree with them.
 *
 * `series` selects the contract month: 0 near, 1 next. The next month is what
 * the rollover figure needs, and it is fetched only when the panel asks.
 */
export function useStockFuturesBoardQuery(series: 0 | 1 = 0, enabled = true) {
  const query = useFuturesBoardQuery({ kind: 'stock', series });
  // `useFuturesBoardQuery` has no `enabled`, and adding one would touch every
  // page that calls it. The next-month board is wanted only while the futures
  // panel is on screen, so the caller gates on this flag instead and the hook
  // still runs — React's rules do not allow conditional hooks either way.
  return enabled ? query : { ...query, data: undefined };
}

/** One symbol's row off the board, or `undefined` when it was not priced. */
export function boardRow(board: FuturesBoard | undefined, symbol: string): FuturesRow | undefined {
  return board?.rows.find((row) => row.symbol === symbol);
}

export type { FuturesBoard, FuturesRow };

export type { HistoryView, Interval };
