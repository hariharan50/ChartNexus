/**
 * View-models the dashboard renders.
 *
 * These are deliberately separate from the wire types in
 * `$contexts/broker-connections/types`: the canonical broker contract carries
 * Decimal-as-string fields and nullable legs, while the UI wants parsed numbers
 * and a flat, presentational shape. `./derive` is the only place that maps one
 * to the other.
 */

import type { DataSourceName } from '$contexts/broker-connections/types';

export type IndexKey = 'NIFTY50' | 'SENSEX' | 'BANKNIFTY';

export type OptionType = 'CE' | 'PE';

export type BuildUp = 'Long Build-up' | 'Short Build-up' | 'Long Unwinding' | 'Short Covering';

export interface IndexQuote {
  key: IndexKey | 'INDIAVIX';
  label: string;
  value: number;
  /** Day change in percent. Absent for a pending or tag-only card. */
  changePercent?: number;
  /** Regime tag used by INDIA VIX (`Calm`, `Elevated`, …). */
  tag?: string;
  /** No backend feed yet — render an "awaiting" state instead of a number. */
  pending?: boolean;
}

/** How the session opened against the previous close. */
export type GapSignal = 'gap_up' | 'gap_down' | 'flat';

/**
 * The session's opening gap, as the backend latched it.
 *
 * The card renders this rather than recomputing it: the opening print is a fact
 * of the session, decided once, and a reading that changes every fifteen
 * seconds was the bug, not the feature.
 */
export interface GapReading {
  /** The index this reading is for, e.g. `NIFTY 50`. */
  label: string;
  open: number;
  previousClose: number;
  /** `open - previousClose`, signed. */
  points: number;
  percent: number;
  signal: GapSignal;
  /** Where this pair came from. `mock` means the card is showing a simulated
      open and must say so; `cached` means a real but earlier reading. */
  source: DataSourceName;
  /** When the pair was observed. Shown so the reader can see it is not ticking. */
  observedAt: Date;
  /** False before the opening auction has produced a real print — the reading
      is the broker's pre-open placeholder and will be replaced. */
  settled: boolean;
}

export interface OptionRow {
  strike: number;
  type: OptionType;
  atm: boolean;
  oi: number;
  oiChange: number;
  ltp: number;
  /** Implied volatility in percent; NaN when the broker omitted it. */
  iv: number;
  buildUp: BuildUp;
}

export type WritingPosture = 'PUT_WRITERS_DOMINANT' | 'CALL_WRITERS_DOMINANT' | 'BALANCED';

export interface OptionsMetrics {
  pcr: number;
  maxPain: number;
  support: number;
  resistance: number;
  writingPosture: WritingPosture;
}

export type Bias = 'Bullish' | 'Bearish' | 'Neutral';

export interface AiBias {
  label: string;
  bias: Bias;
  /** Model confidence in percent, once a model exists to produce it. */
  confidence?: number;
}

export interface AiSummary {
  biases: AiBias[];
  /** India VIX — omitted until a VIX feed lands. */
  vix?: number;
  pcr: number;
  support: number;
  resistance: number;
}

/** How each build-up tag maps to the market-semantic colour set. */
export function buildUpTone(buildUp: BuildUp): 'bullish' | 'bearish' | 'warning' | 'accent' {
  switch (buildUp) {
    case 'Long Build-up':
      return 'bullish';
    case 'Short Build-up':
      return 'bearish';
    case 'Long Unwinding':
      return 'warning';
    case 'Short Covering':
      return 'accent';
  }
}
