/** Wire shapes for the Future Lab's universe-wide reads. */

/**
 * Where a contract sits in the price-vs-open-interest 2x2.
 *
 * Rising OI means money entering the contract, so price direction says which
 * side is doing it; falling OI means positions closing, so price direction says
 * which side is capitulating. `neutral` is not a fifth quadrant — it is the
 * backend declining to read direction into a move too small to mean anything.
 */
export type BuildupState =
  'long_buildup' | 'short_buildup' | 'short_covering' | 'long_unwinding' | 'neutral';

export interface FuturesRow {
  symbol: string;
  name: string | null;
  price: string;
  /**
   * Null when the contract had no prior close to measure against. It must be
   * rendered as "no data" and never as 0.00% — those are different claims.
   */
  price_change_percent: string | null;
  /** Null when the feed carries no open interest for this contract. */
  open_interest: number | null;
  oi_change_percent: string | null;
  state: BuildupState;
  /** 'index' or 'stock', so a view can take one half of the universe. */
  kind: 'index' | 'stock' | null;
  lot_size: number | null;
  volume: number | null;
  /**
   * Null whenever yesterday's volume is unknown — the normal case on live
   * data, since no broker payload carries it. Render as "no data", not 0.00%.
   */
  volume_change_percent: string | null;
  /** 'O=L' | 'O=H', or null when the day's prints do not answer it. */
  open_marker: string | null;
  sector: string | null;
}

/** The six panels, plus how much of the universe they were drawn from. */
export interface FuturesDashboard {
  top_gainers: FuturesRow[];
  top_losers: FuturesRow[];
  long_buildup: FuturesRow[];
  short_buildup: FuturesRow[];
  short_covering: FuturesRow[];
  long_unwinding: FuturesRow[];
  covered: number;
  universe: number;
  /**
   * Where the numbers came from. A simulated board looks identical to a real
   * one, so this is the only thing that distinguishes them — never render a
   * board without surfacing it.
   */
  source?: 'live' | 'cached' | 'mock';
  /**
   * ISO date of the contract series these rows belong to — the one most of
   * them share, since NSE and BSE settle on different days. Absent on an API
   * predating the field.
   */
  expiry?: string | null;
  /** Which series was drawn: 0 near month, 1 next, 2 far. */
  series?: number;
  /**
   * False when no open-interest sweep covers this series. Every row then
   * reads `neutral` and the build-up panels are empty **because nothing was
   * measured**, not because nothing happened — a page that does not say which
   * is showing the reader a market that does not exist.
   */
  has_open_interest?: boolean;
}

export interface FuturesBoard {
  rows: FuturesRow[];
  covered: number;
  universe: number;
  /** Absent on an API predating the field. Never default it — labelling
   *  unknown provenance as "mock" or "live" is exactly the confusion the
   *  badge exists to prevent; show nothing instead. */
  source?: 'live' | 'cached' | 'mock';
  /**
   * ISO date of the contract series these rows belong to — the one most of
   * them share, since NSE and BSE settle on different days. Absent on an API
   * predating the field.
   */
  expiry?: string | null;
  /** Which series was drawn: 0 near month, 1 next, 2 far. */
  series?: number;
  /**
   * False when no open-interest sweep covers this series. Every row then
   * reads `neutral` and the build-up panels are empty **because nothing was
   * measured**, not because nothing happened — a page that does not say which
   * is showing the reader a market that does not exist.
   */
  has_open_interest?: boolean;
}

/**
 * One contract series the Future Lab can be pointed at.
 *
 * Addressed by `series` rather than by date, and that is the whole design:
 * expiry dates do not agree across the universe — NSE and BSE settle on
 * different days — so no single date could name the same contract for every
 * row on a board. `expiry` is the date **most** instruments settle that series
 * on, which makes it a label, not a key.
 */
export interface ExpiryOption {
  series: number;
  expiry: string;
}

export interface ExpiryList {
  expiries: ExpiryOption[];
}
