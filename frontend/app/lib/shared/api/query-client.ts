import { QueryClient } from '@tanstack/react-query';
import { isApiError } from './errors';

/**
 * Defaults are tuned for market data: values go stale quickly, and the
 * websocket — not polling — is what keeps them fresh. Retrying a 4xx just
 * multiplies a request the server already refused.
 */
export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 15_000,
        gcTime: 5 * 60_000,
        refetchOnWindowFocus: true,
        refetchOnReconnect: true,
        retry: (failureCount, error) => {
          if (isApiError(error) && error.isTerminal) return false;
          return failureCount < 2;
        },
        retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 8000)
      },
      mutations: {
        retry: false
      }
    }
  });
}

/**
 * Query keys are declared centrally so realtime updates can invalidate exactly
 * the right slice of cache without guessing at key shapes.
 */
export const queryKeys = {
  session: () => ['session'] as const,
  // The catalog is cached per scope ('' for the whole universe, or a kind
  // like 'index'), not per keystroke: filtering happens client-side.
  instruments: (scope?: string) => ['instruments', scope ?? ''] as const,
  marketStatus: () => ['market-status'] as const,
  spot: (symbol: string) => ['spot', symbol] as const,
  optionChain: (symbol: string, expiry: string) => ['option-chain', symbol, expiry] as const,
  optionMetrics: (symbol: string, expiry: string, metric: string) =>
    ['option-metrics', symbol, expiry, metric] as const,
  futures: (symbol: string) => ['futures', symbol] as const,
  signals: (params: Record<string, unknown> = {}) => ['signals', params] as const,
  dashboard: (symbol: string) => ['dashboard', symbol] as const
} as const;
