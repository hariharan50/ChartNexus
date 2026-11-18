import { apiFetch } from '$shared/api/client';
import type {
  BrokerAuthorization,
  BrokerConnection,
  BrokerConnections,
  BrokerName,
  ExpiryList,
  FuturesQuote,
  MarketStatus,
  OptionChain,
  Quote
} from './types';

/**
 * Broker connection management. Every call names its broker; FYERS is the
 * default so existing callers keep working.
 */

export function listConnections(fetcher?: typeof fetch): Promise<BrokerConnections> {
  return apiFetch<BrokerConnections>({ url: '/broker/connections', fetcher });
}

export function getConnection(
  broker: BrokerName = 'fyers',
  fetcher?: typeof fetch
): Promise<BrokerConnection> {
  return apiFetch<BrokerConnection>({ url: `/broker/${broker}/status`, fetcher });
}

export function saveCredentials(
  appId: string,
  secretId: string,
  broker: BrokerName = 'fyers',
  clientId?: string
): Promise<BrokerConnection> {
  return apiFetch<BrokerConnection>({
    url: `/broker/${broker}/credentials`,
    method: 'POST',
    body: JSON.stringify({ app_id: appId, secret_id: secretId, client_id: clientId || null })
  });
}

export function startConnect(
  redirectTo?: string,
  broker: BrokerName = 'fyers'
): Promise<BrokerAuthorization> {
  return apiFetch<BrokerAuthorization>({
    url: `/broker/${broker}/connect`,
    method: 'POST',
    body: JSON.stringify({ redirect_to: redirectTo ?? null })
  });
}

export function completeConnect(
  authCode: string,
  state: string,
  broker: BrokerName = 'fyers'
): Promise<BrokerConnection> {
  return apiFetch<BrokerConnection>({
    url: `/broker/${broker}/callback`,
    method: 'POST',
    body: JSON.stringify({ auth_code: authCode, state })
  });
}

export function disconnect(broker: BrokerName = 'fyers'): Promise<BrokerConnection> {
  return apiFetch<BrokerConnection>({ url: `/broker/${broker}/connection`, method: 'DELETE' });
}

export function revokeCredentials(broker: BrokerName = 'fyers'): Promise<BrokerConnection> {
  return apiFetch<BrokerConnection>({ url: `/broker/${broker}/credentials`, method: 'DELETE' });
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

export function getExpiries(instrument: string, fetcher?: typeof fetch): Promise<ExpiryList> {
  return apiFetch<ExpiryList>({ url: '/market/expiries', params: { instrument }, fetcher });
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
