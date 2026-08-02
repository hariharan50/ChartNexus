/**
 * Mirrors `contexts/broker_connections/api/schemas.py` and the market-data
 * schemas. No field here can hold a token or secret — the API has none to give.
 */

export type ConnectionStatus = 'pending' | 'active' | 'expired' | 'revoked';

export interface BrokerConnection {
  broker: string;
  status: ConnectionStatus;
  /** Credentials are stored, so Connect can be offered. */
  configured: boolean;
  /** The broker accepted our token the last time we asked. */
  connected: boolean;
  masked_app_id: string | null;
  redirect_uri: string;
  display_name: string | null;
  broker_user_id: string | null;
  connected_at: string | null;
  last_validated_at: string | null;
  last_error: string | null;
}

export interface BrokerAuthorization {
  authorization_url: string;
  state: string;
  expires_in_seconds: number;
}

/** Where a payload actually came from. Never assume `live`. */
export type DataSourceName = 'live' | 'cached' | 'mock';

export interface Provenance {
  source: DataSourceName;
  fetched_at: string;
  age_seconds: number;
  is_stale: boolean;
}

export interface MarketStatus {
  is_open: boolean;
  session_date: string;
  time_ist: string;
  provider: string;
  connected: boolean;
  source: DataSourceName;
  market_open: string;
  market_close: string;
}

export interface Quote {
  instrument: string;
  price: string;
  change: string | null;
  change_percent: string | null;
  provenance: Provenance;
}

export interface OptionQuote {
  ltp: string;
  oi: number;
  oi_change: number;
  volume: number;
  iv: string | null;
  bid: string | null;
  ask: string | null;
  delta: string | null;
}

export interface StrikeRow {
  strike: string;
  ce: OptionQuote | null;
  pe: OptionQuote | null;
}

export interface OptionChain {
  instrument: string;
  expiry: string;
  expiries: string[];
  spot_price: string;
  atm_strike: string | null;
  pcr: string | null;
  lot_size: number | null;
  change_percent: string | null;
  future_price: string | null;
  total_call_oi: number;
  total_put_oi: number;
  strikes: StrikeRow[];
  provenance: Provenance;
}
