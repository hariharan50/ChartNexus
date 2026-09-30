import type { DataSourceName } from '$contexts/broker-connections/types';

/**
 * Wire types for PMS — the pre-market screener.
 *
 * Mirrors `contexts/pre_market/api/schemas.py`. Three conventions carry
 * through, two shared with GIA and one this page adds:
 *
 * * **Decimals arrive as JSON strings**, so numeric fields are `WireNumber`
 *   and go through `toNumber` before any arithmetic.
 * * **`null` means "not known", never zero.** A figure that did not arrive
 *   renders as a dash; coercing it to 0 turns "we do not know" into "it did
 *   not move".
 * * **Every percentage arrives with its denominator.** Breadth carries counts,
 *   the regime carries `inputs_present`/`inputs_total`, and the VIX percentile
 *   carries `vix_sample_sessions`. A component that renders a bare percentage
 *   off this contract is going against the grain on purpose.
 */

/** A `Decimal` on the wire. Never do maths on it directly — see `toNumber`. */
export type WireNumber = string | number;

/** Whether a panel's data arrived, and if not, why. */
export type Availability = 'ok' | 'degraded' | 'unavailable';

export interface SectionStatus {
  availability: Availability;
  /** Present whenever the panel is not `ok`. Rendered verbatim to the reader. */
  reason: string | null;
}

export type GapBucket = 'gap_down_large' | 'gap_down' | 'flat' | 'gap_up' | 'gap_up_large';

/** Which yardstick bucketed the gap — ATR where available, percent otherwise. */
export type GapBasis = 'atr' | 'percent';

export type Stance = 'bullish' | 'bearish' | 'neutral';

export type RegimeBand =
  'strongly_bearish' | 'bearish' | 'neutral' | 'bullish' | 'strongly_bullish';

export type RegimeAxis = 'trend' | 'momentum' | 'volatility' | 'breadth' | 'global' | 'derivatives';

/** How a level was derived. Confluence only counts across *different* origins. */
export type LevelOrigin =
  | 'pivot'
  | 'central_pivot'
  | 'prior_day'
  | 'weekly'
  | 'monthly'
  | 'yearly'
  | 'option_wall'
  | 'max_pain'
  | 'gamma_flip';

export type LevelSide = 'above' | 'below' | 'at';

export interface Gap {
  points: WireNumber;
  percent: WireNumber;
  bucket: GapBucket;
  basis: GapBasis;
  atr_multiple: number | null;
  reference_close: WireNumber;
}

export interface HeadlineCard {
  symbol: string;
  label: string;
  price: WireNumber | null;
  change: WireNumber | null;
  change_percent: WireNumber | null;
  previous_close: WireNumber | null;
  /** The realised gap. `null` before the market opens — never back-filled. */
  gap: Gap | null;
  /** What GIFT is quoting. Only ever set for NIFTY. */
  implied_gap: Gap | null;
  /** `false` for SENSEX: no constituent weight table exists for it. */
  breadth_tracked: boolean;
  source: DataSourceName;
}

export interface LevelRow {
  label: string;
  price: number;
  origin: LevelOrigin;
  side: LevelSide;
  distance_points: number;
  distance_percent: number;
  /** `null` when no ATR was available — not 0, which would read as "here". */
  distance_atr: number | null;
}

export interface LevelClusterRow {
  price: number;
  labels: string[];
  origins: LevelOrigin[];
}

export interface PeriodRange {
  high: number;
  low: number;
  /** How many bars went into it. A 52-week high off eleven bars is not one. */
  bars: number;
}

export interface Levels {
  spot: number;
  pivot: number | null;
  r1: number | null;
  r2: number | null;
  r3: number | null;
  s1: number | null;
  s2: number | null;
  s3: number | null;
  cpr_top: number | null;
  cpr_bottom: number | null;
  cpr_width_percent: number | null;
  prior_day_high: number | null;
  prior_day_low: number | null;
  prior_day_close: number | null;
  week: PeriodRange | null;
  month: PeriodRange | null;
  year: PeriodRange | null;
  /** Ordered high to low — the client renders a ladder without sorting. */
  ladder: LevelRow[];
  clusters: LevelClusterRow[];
  nearest_above: LevelRow | null;
  nearest_below: LevelRow | null;
}

export interface Technicals {
  ema20: number | null;
  ema50: number | null;
  ema100: number | null;
  ema200: number | null;
  /** `null` for a mixed stack — "the averages disagree" is a real state. */
  ema_stacked_up: boolean | null;
  rsi14: number | null;
  adx14: number | null;
  atr14: number | null;
  atr_percent: number | null;
  bollinger_width: number | null;
  realized_vol20: number | null;
}

export interface Volatility {
  india_vix: WireNumber | null;
  india_vix_change_percent: WireNumber | null;
  vix_percentile: number | null;
  /** Printed beside the percentile. It is why the rank may be null. */
  vix_sample_sessions: number;
  atm_iv: WireNumber | null;
  iv_percentile: WireNumber | null;
}

export interface MoveEstimate {
  basis: 'straddle' | 'vix' | 'atr';
  points: number;
  percent: number;
  upper: number;
  lower: number;
}

export interface ExpectedMove {
  spot: number;
  /** The three are reported side by side and must never be averaged. */
  straddle: MoveEstimate | null;
  vix: MoveEstimate | null;
  atr: MoveEstimate | null;
  days_to_expiry: number | null;
  /** Set only when the measures disagree materially. The gap is the reading. */
  note: string | null;
}

export interface OptionsPositioning {
  days_to_expiry: number | null;
  atm_strike: WireNumber | null;
  pcr_oi: WireNumber | null;
  pcr_change: WireNumber | null;
  total_call_oi: number | null;
  total_put_oi: number | null;
  max_pain: WireNumber | null;
  /** Where positioning sits — never presented as a level that will hold. */
  call_wall: WireNumber | null;
  put_wall: WireNumber | null;
  gamma_flip: WireNumber | null;
  atm_iv: WireNumber | null;
  atm_straddle: WireNumber | null;
}

export interface Contribution {
  key: string;
  label: string;
  region: string;
  change_percent: WireNumber;
  points: WireNumber;
}

export interface Gift {
  level: WireNumber | null;
  change: WireNumber | null;
  change_percent: WireNumber | null;
  overnight_high: WireNumber | null;
  overnight_low: WireNumber | null;
  gap_points: WireNumber | null;
  gap_percent: WireNumber | null;
  signal: string | null;
}

export interface GlobalCues {
  pressure_score: WireNumber | null;
  pressure_band: string | null;
  contributions: Contribution[];
  /** Weighted markets with no quote — named, never silently dropped. */
  missing: string[];
  macro: Contribution[];
  gift: Gift | null;
}

export interface Breadth {
  advances: number | null;
  declines: number | null;
  unchanged: number | null;
  /** The denominator. Twelve members move a percentage in 8.3% steps. */
  priced: number | null;
  universe: number | null;
}

export interface Flows {
  session_date: string | null;
  fii_net: WireNumber | null;
  dii_net: WireNumber | null;
}

export interface RegimeFactor {
  key: string;
  label: string;
  axis: RegimeAxis;
  stance: Stance;
  points: number;
  /** The raw input. Without it the score cannot be argued with. */
  reading: string;
  note: string | null;
}

export interface RegimeAxisRead {
  axis: RegimeAxis;
  label: string;
  stance: Stance;
  points: number;
  resolved: boolean;
  factors: RegimeFactor[];
}

export interface Regime {
  score: number;
  band: RegimeBand;
  /** Derived from coverage, never from how extreme the score is. */
  confidence: 'thin' | 'moderate' | 'high';
  inputs_present: number;
  inputs_total: number;
  axes: RegimeAxisRead[];
  factors: RegimeFactor[];
}

export interface Narrative {
  markdown: string;
  trading_day: string;
  generated_at: string | null;
  source: string;
}

export interface MarketPhaseInfo {
  is_open: boolean;
  session_date: string;
  time_ist: string;
  opens_ist: string;
  closes_ist: string;
}

export interface Statuses {
  headline: SectionStatus;
  levels: SectionStatus;
  technicals: SectionStatus;
  volatility: SectionStatus;
  expected_move: SectionStatus;
  options: SectionStatus;
  global_cues: SectionStatus;
  breadth: SectionStatus;
  flows: SectionStatus;
  regime: SectionStatus;
  narrative: SectionStatus;
}

export interface PreMarketView {
  as_of: string;
  phase: MarketPhaseInfo;
  focus: string;
  focus_label: string;
  /** The weakest leg's provenance — the page is only as live as its worst. */
  source: DataSourceName;
  status: Statuses;
  headline: HeadlineCard[];
  levels: Levels | null;
  technicals: Technicals | null;
  volatility: Volatility | null;
  expected_move: ExpectedMove | null;
  options: OptionsPositioning | null;
  global_cues: GlobalCues | null;
  breadth: Breadth | null;
  flows: Flows | null;
  regime: Regime | null;
  narrative: Narrative | null;
}
