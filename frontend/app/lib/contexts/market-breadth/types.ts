import type { DataSourceName } from '$contexts/broker-connections/types';

/**
 * Wire types for the Future Lab → Analysis pages.
 *
 * Mirrors `contexts/market_breadth/api/schemas.py`. Two conventions carry
 * through every shape here and the pages depend on both:
 *
 * * **Money is rupees crore and percentages are already 0-100.** The client
 *   formats; it never converts.
 * * **`null` means "not known", never zero.** A member with no previous close,
 *   a DII line the exchange does not publish, an index whose level the board
 *   could not read — all of them arrive as `null`, and every one must render
 *   as a dash. Coercing them to 0 turns "we do not know" into "it did not
 *   move", which is the one lie these pages exist to avoid telling.
 *
 * Decimals arrive as JSON strings (FastAPI serialises `Decimal` that way), so
 * numeric fields are typed `string | number` and go through `toNumber` before
 * any arithmetic.
 */

/** A `Decimal` on the wire. Never do maths on it directly — see `toNumber`. */
export type WireNumber = string | number;

// -- FII/DII -----------------------------------------------------------------

export type FlowSegment =
  'cash' | 'index_futures' | 'index_options' | 'stock_futures' | 'stock_options';

export interface ParticipantFlow {
  buy: WireNumber;
  sell: WireNumber;
  net: WireNumber;
}

export interface SegmentFlow {
  segment: FlowSegment;
  fii: ParticipantFlow;
  /** Null in every derivative segment — the published file carries no DII line. */
  dii: ParticipantFlow | null;
}

export type OiParticipant = 'fii' | 'dii' | 'pro' | 'client';

/**
 * The book behind a net, in contracts.
 *
 * Futures fill `long`/`short`; options fill the four option legs. The other
 * pair is `null`, not zero — an options book has no "long" column at all.
 */
export interface OiLegs {
  long: number | null;
  short: number | null;
  call_long: number | null;
  call_short: number | null;
  put_long: number | null;
  put_short: number | null;
  total: number;
}

/**
 * One participant's position in one segment.
 *
 * **Contracts, not crores.** This is a different measurement from the value
 * figures above and the two are not comparable: a participant can be a net
 * buyer on the day and still hold a net short book.
 */
export interface OiRow {
  participant: OiParticipant;
  segment: FlowSegment;
  net: number;
  previous_net: number;
  change: number;
  legs: OiLegs | null;
}

/** One band of the board — a participant's segments, or a segment's participants. */
export interface OiGroup {
  /** The participant or segment id, depending on which grouping this is. */
  key: string;
  rows: OiRow[];
  net: number;
  change: number;
}

/** Where the benchmark stood. Present only for the latest session. */
export interface SummaryIndex {
  index: string;
  level: WireNumber | null;
  change_percent: WireNumber | null;
  source: DataSourceName;
  basis: string;
}

export interface FlowSummary {
  /** ISO date, or null when nothing has been published yet. */
  session_date: string | null;
  segments: SegmentFlow[];
  fii_cash_week: WireNumber;
  fii_cash_month: WireNumber;
  dii_cash_week: WireNumber;
  dii_cash_month: WireNumber;
  /** Signed run of same-side cash sessions: +4 is four days of net buying. */
  fii_cash_streak: number;
  dii_cash_streak: number;
  sessions: number;
  source: DataSourceName;
  /** The same open-interest board in two groupings — the page's view toggle. */
  by_participant: OiGroup[];
  by_segment: OiGroup[];
  /**
   * How far each segment's four nets are from summing to zero. Zero
   * everywhere on a complete board, because every long is somebody's short.
   */
  imbalance: Record<string, number>;
  /**
   * The published sessions either side of this one. Step with these rather
   * than computing a date — the first holiday lands a computed "yesterday" on
   * an empty board.
   */
  previous_session: string | null;
  next_session: string | null;
  index: SummaryIndex | null;
}

export interface CashDay {
  session_date: string;
  fii_buy: WireNumber;
  fii_sell: WireNumber;
  fii_net: WireNumber;
  dii_buy: WireNumber;
  dii_sell: WireNumber;
  dii_net: WireNumber;
  /** Running net from the first session **in this window**, not any epoch. */
  fii_cumulative: WireNumber;
  dii_cumulative: WireNumber;
}

export interface CashFlowHistory {
  days: CashDay[];
  fii_total: WireNumber;
  dii_total: WireNumber;
  source: DataSourceName;
}

// -- index -------------------------------------------------------------------

export interface IndexHeader {
  index: string;
  level: WireNumber | null;
  previous_close: WireNumber | null;
  change_absolute: WireNumber | null;
  change_percent: WireNumber | null;
  /** Members that produced a usable reading, against what the index holds. */
  covered: number;
  universe: number;
  /** Index weight those members account for. 94 means 6% went unpriced. */
  covered_weight_percent: WireNumber;
  source: DataSourceName;
  as_of: string | null;
  /** "cash" or "futures" — which market the member prices came from. */
  basis: string;
}

export interface Contribution {
  symbol: string;
  name: string | null;
  sector: string | null;
  last: WireNumber;
  change_percent: WireNumber;
  /** Renormalised over the priced members, so these sum to 100. */
  weight_percent: WireNumber;
  /** Index points this member pushed the index. */
  points: WireNumber;
}

export interface ContributorsView {
  header: IndexHeader;
  gainers: Contribution[];
  losers: Contribution[];
  modelled_points: WireNumber;
  actual_points: WireNumber | null;
  /** The index's move minus the modelled contributions. Shown, not hidden. */
  gap: WireNumber | null;
}

export interface BreadthCount {
  advancing: number;
  declining: number;
  unchanged: number;
  /** Members with no price at all — a different fact from `unchanged`. */
  unpriced: number;
  /** Advances per decline; null when nothing declined. */
  ratio: WireNumber | null;
  advancing_percent: WireNumber | null;
  net: number;
}

export interface IndexMember {
  symbol: string;
  name: string | null;
  sector: string | null;
  last: WireNumber;
  previous_close: WireNumber | null;
  change_absolute: WireNumber | null;
  change_percent: WireNumber | null;
  weight_percent: WireNumber;
}

export interface SectorBreadth {
  sector: string;
  count: BreadthCount;
  weight_percent: WireNumber;
  weighted_change_percent: WireNumber | null;
  members: IndexMember[];
}

export interface AdvanceDeclineView {
  header: IndexHeader;
  overall: BreadthCount;
  sectors: SectorBreadth[];
  members: IndexMember[];
}

export interface WeightSlice {
  label: string;
  name: string | null;
  weight_percent: WireNumber;
  /** Share of the priced index — what the donut draws. */
  share_percent: WireNumber;
  change_percent: WireNumber | null;
  members: number;
}

export interface WeightageView {
  header: IndexHeader;
  members: WeightSlice[];
  sectors: SectorBreadth[];
}

export type RotationQuadrant = 'leading' | 'improving' | 'weakening' | 'lagging';

export interface SectorPosition {
  sector: string;
  change_percent: WireNumber;
  /** Sector move minus the index move, percentage points — the x axis. */
  relative_strength: WireNumber;
  participation_percent: WireNumber;
  /** `participation_percent - 50`, so the plot's origin is neutral — the y axis. */
  participation_offset: WireNumber;
  weight_percent: WireNumber;
  advancing: number;
  declining: number;
  members: number;
  quadrant: RotationQuadrant;
  leaders: string[];
  laggards: string[];
}

export interface SectorRotationView {
  header: IndexHeader;
  sectors: SectorPosition[];
}
