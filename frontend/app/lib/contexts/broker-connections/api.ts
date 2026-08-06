import { apiFetch } from '$shared/api/client';
import type {
  BrokerAuthorization,
  BrokerConnection,
  FuturesQuote,
  MarketStatus,
  OptionChain,
  Quote
} from './types';

/** Broker connection management. */

export function getConnection(fetcher?: typeof fetch): Promise<BrokerConnection> {
  return apiFetch<BrokerConnection>({ url: '/broker/fyers/status', fetcher });
}

export function saveCredentials(appId: string, secretId: string): Promise<BrokerConnection> {
  return apiFetch<BrokerConnection>({
    url: '/broker/fyers/credentials',
    method: 'POST',
    body: JSON.stringify({ app_id: appId, secret_id: secretId })
  });
}

export function startConnect(redirectTo?: string): Promise<BrokerAuthorization> {
  return apiFetch<BrokerAuthorization>({
    url: '/broker/fyers/connect',
    method: 'POST',
    body: JSON.stringify({ redirect_to: redirectTo ?? null })
  });
}

export function completeConnect(authCode: string, state: string): Promise<BrokerConnection> {
  return apiFetch<BrokerConnection>({
    url: '/broker/fyers/callback',
    method: 'POST',
    body: JSON.stringify({ auth_code: authCode, state })
  });
}

export function disconnect(): Promise<BrokerConnection> {
  return apiFetch<BrokerConnection>({ url: '/broker/fyers/connection', method: 'DELETE' });
}

export function revokeCredentials(): Promise<BrokerConnection> {
  return apiFetch<BrokerConnection>({ url: '/broker/fyers/credentials', method: 'DELETE' });
}

/** Market data. */

export function getMarketStatus(fetcher?: typeof fetch): Promise<MarketStatus> {
  return apiFetch<MarketStatus>({ url: '/market/status', fetcher });
}

export function getSpot(instrument: string, fetcher?: typeof fetch): Promise<Quote> {
  return apiFetch<Quote>({ url: '/market/spot', params: { instrument }, fetcher });
}

export function getFutures(instrument: string, fetcher?: typeof fetch): Promise<FuturesQuote> {
  return apiFetch<FuturesQuote>({ url: '/market/futures', params: { instrument }, fetcher });
}

export function getOptionChain(
  instrument: string,
  expiry?: string,
  fetcher?: typeof fetch
): Promise<OptionChain> {
  return apiFetch<OptionChain>({
    url: '/market/option-chain',
    params: { instrument, expiry },
    fetcher
  });
}
