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

/**
 * Where a payload actually came from. Never assume `live`.
 *
 * `unavailable` is not a fourth kind of data — it is the absence of any. A
 * caller that refused simulated values (`live_only`) and found nothing real
 * gets an empty payload stamped this way, so "we have no bars" is a state the
 * UI can render rather than something it has to infer from a zero-length array.
 */
export type DataSourceName = 'live' | 'cached' | 'mock' | 'unavailable';

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

export type GapSignalName = 'gap_up' | 'gap_down' | 'flat';

/**
 * The session's opening gap, latched by the backend.
 *
 * Not derived from `day_open` and `previous_close` below: those carry whatever
 * the latest poll returned, so a poll that degraded to simulated data rewrote
 * them and the card flipped sign between refreshes. This is the first
 * believable pair of the session, frozen, and it says where it came from.
 */
export interface SessionGap {
  opened_at: string;
  reference_close: string;
  points: string;
  percent: string;
  signal: GapSignalName;
  /** Provenance of this pair, which can differ from the quote's once the
      broker degrades — the gap holds its live reading, the price does not. */
  source: DataSourceName;
  observed_at: string;
  /** False while the opening auction has not yet produced a real print. */
  settled: boolean;
}

export interface Quote {
  instrument: string;
  price: string;
  change: string | null;
  change_percent: string | null;
  /** The session's opening print and the prior session's close, as the latest
      payload reported them. Read `gap` for the overnight gap — these two move
      with the feed. */
  day_open: string | null;
  previous_close: string | null;
  /** The latched opening gap. `null` until the session has a believable pair. */
  gap: SessionGap | null;
  provenance: Provenance;
}

export interface FuturesQuote {
  instrument: string;
  /** Broker symbol of the active monthly contract, e.g. `NSE:NIFTY25AUGFUT`. */
  contract: string;
  /** ISO expiry date of that contract. */
  expiry: string;
  price: string;
  change: string | null;
  change_percent: string | null;
  volume: number;
  day_high: string | null;
  day_low: string | null;
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

/**
 * The instrument's listed expiries, oldest first.
 *
 * Separate from `OptionChain.expiries`, which only comes attached to a whole
 * chain: a page that just needs to populate an expiry picker should not pay for
 * three hundred strikes to read eight dates off the end of them.
 */
export interface ExpiryList {
  instrument: string;
  expiries: string[];
  provenance: Provenance;
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
  india_vix: string | null;
  india_vix_change_percent: string | null;
  iv_percentile: string | null;
  total_call_oi: number;
  total_put_oi: number;
  strikes: StrikeRow[];
  provenance: Provenance;
}
