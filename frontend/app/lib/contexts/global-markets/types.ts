import type { DataSourceName } from '$contexts/broker-connections/types';

/**
 * Wire types for GIA — Global Index Analysis.
 *
 * Mirrors `contexts/global_markets/api/schemas.py`. Two conventions carry
 * through every shape here, the same two the market-breadth contract uses:
 *
 * * **Decimals arrive as JSON strings** (FastAPI serialises `Decimal` that
 *   way), so numeric fields are typed `WireNumber` and go through `toNumber`
 *   before any arithmetic.
 * * **`null` means "not known", never zero.** A market the provider could not
 *   price arrives as `null` and must render as a dash. Coercing it to 0 turns
 *   "we do not know" into "it did not move" — on a page whose entire job is
 *   reading direction, that is the worst possible lie.
 */

/** A `Decimal` on the wire. Never do maths on it directly — see `toNumber`. */
export type WireNumber = string | number;

export type RegionId = 'asia' | 'europe' | 'americas' | 'india' | 'macro';

/** Whether a market's session has run yet, within the overnight window. */
export type BandState = 'pending' | 'live' | 'closed';

/** Where the weighted composite lands. */
export type PressureBand = 'strong_down' | 'down' | 'flat' | 'up' | 'strong_up';

/** Same vocabulary as the dashboard's gap card, by design. */
export type GapSignal = 'gap_up' | 'gap_down' | 'flat';

/**
 * Whether the composite and GIFT tell the same story. `disagree` is the most
 * informative state on the page, not an error.
 */
export type Verdict = 'agree' | 'disagree' | 'unknown';

export interface MarketRow {
  key: string;
  label: string;
  region: RegionId;
  /** Context beside the board rather than a scored input. */
  macro: boolean;
  price: WireNumber | null;
  change: WireNumber | null;
  change_percent: WireNumber | null;
  previous_close: WireNumber | null;
  /** Recent closes, oldest first. Empty when no series was available. */
  spark: WireNumber[];
  /** The market's session in IST, or `24h` for FX and futures. */
  opens_ist: string;
  closes_ist: string;
}

export interface SessionBandRow {
  key: string;
  label: string;
  region: RegionId;
  opens_at: string;
  closes_at: string;
  state: BandState;
  /** 0–1 positions on the overnight axis; the client does no date maths. */
  start_fraction: number;
  end_fraction: number;
  change_percent: WireNumber | null;
}

export interface ContributionRow {
  key: string;
  label: string;
  region: RegionId;
  change_percent: WireNumber;
  weight: WireNumber;
  /** How much the move still counts, by how long ago the market closed. */
  recency: WireNumber;
  /** The signed points this market put into the composite. */
  points: WireNumber;
}

export interface Pressure {
  score: WireNumber;
  band: PressureBand;
  contributions: ContributionRow[];
  /** Weighted markets with no usable quote — named, never silently dropped. */
  missing: string[];
}

export interface ImpliedOpen {
  gift_level: WireNumber;
  nifty_spot: WireNumber;
  /** Where NIFTY last settled — the base the gap is measured from. */
  nifty_previous_close: WireNumber;
  /** GIFT against *spot*, which is a different number intraday. */
  basis: WireNumber;
  implied_level: WireNumber;
  gap_points: WireNumber;
  gap_percent: WireNumber;
  signal: GapSignal;
}

export interface OvernightWindow {
  opened_at: string;
  closes_at: string;
  target_session: string;
  /** 0–1: how far through the window "now" is. */
  progress: number;
}

export interface RegionRow {
  region: RegionId;
  label: string;
  change_percent: WireNumber | null;
  members: number;
}

export interface GlobalView {
  as_of: string;
  window: OvernightWindow;
  markets: MarketRow[];
  regions: RegionRow[];
  bands: SessionBandRow[];
  pressure: Pressure;
  implied: ImpliedOpen | null;
  gift: MarketRow | null;
  verdict: Verdict;
  source: DataSourceName;
  /** Separate from `source`: GIFT is simulated until a live feed exists. */
  gift_source: DataSourceName;
  region_labels: Record<string, string>;
}
