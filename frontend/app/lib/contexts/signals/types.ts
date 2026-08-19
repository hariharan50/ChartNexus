/**
 * Hand-written types mirroring the backend `signals` and `copilot` schemas.
 *
 * The OpenAPI contract is empty and orval has never run, so — like the other
 * contexts — these are maintained by hand alongside the Pydantic responses.
 */

import type { DataSourceName } from '$contexts/broker-connections/types';

export type Decision = 'BUY' | 'SELL' | 'HOLD';

export type Horizon = 'intraday' | 'end_of_day' | 'swing';

/** One horizon's calibrated call — the unit the horizon switcher renders. */
export interface HorizonCall {
  horizon: Horizon;
  decision: Decision;
  /** Model p(up-move) in [0, 1]. */
  probability: number;
  /** Calibrated 0-100 conviction (measured hit-rate, scaled by coverage). */
  confidence: number;
  /** Features that moved this call most, strongest first. */
  drivers: string[];
}

export interface Levels {
  spot: number;
  support: number | null;
  resistance: number | null;
  max_pain: number | null;
  gamma_flip: number | null;
  call_wall: number | null;
  put_wall: number | null;
}

export interface MarketContext {
  india_vix: number | null;
  india_vix_change_percent: number | null;
  pcr: number | null;
}

export interface Scaffold {
  entry: number | null;
  stop: number | null;
  target: number | null;
  risk_reward: number | null;
  suggested_contract: string | null;
}

export interface Guidance {
  symbol: string;
  /** Headline (intraday) call, echoed at top level for back-compat. */
  decision: Decision;
  confidence: number;
  score: number;
  /** Market regime the call was made in (trending up/down, rangebound). */
  regime: string;
  provenance: DataSourceName;
  is_actionable: boolean;
  rationale: string;
  expiry_ref: string | null;
  warnings: string[];
  /** One calibrated call per horizon (intraday / end-of-day / swing). */
  horizons: HorizonCall[];
  /** Shared market backdrop for the context cards (VIX, PCR). */
  context: MarketContext;
  levels: Levels;
  scaffold: Scaffold;
}

export interface AskResponse {
  answer: string;
  symbol: string;
}

/** Whether the AI Console is usable — false when no LLM key is configured. */
export interface AgentAvailability {
  available: boolean;
}

export interface HistoryItem {
  generated_at: string;
  symbol: string;
  decision: Decision;
  confidence: number;
  score: number;
  provenance: DataSourceName;
}

export interface GuidanceHistory {
  symbol: string;
  items: HistoryItem[];
}

/** One STRYX call logged today, as returned by the journal endpoint. */
export interface StryxJournalCall {
  created_at: string;
  instrument: string | null;
  entry_style: string | null;
  status: 'LIVE' | 'NO_TRADE' | 'WATCHING';
  entry: string | null;
  stop: string | null;
  target1: string | null;
  target2: string | null;
  confidence: string | null;
  reasoning: string | null;
}

/** Today's STRYX journal + the remaining LIVE-call budget (drives the UI chip). */
export interface StryxJournalToday {
  live_count: number;
  cap: number;
  remaining: number;
  calls: StryxJournalCall[];
}

/** A tool Hella reached for while answering, shown as a chip in her bubble. */
export interface ChatTool {
  name: string;
  title: string;
  done: boolean;
}

/** A rendered chat turn in the console. */
export interface ChatMessage {
  id: string;
  role: 'user' | 'agent';
  text: string;
  /** Skills the planner chose for this turn (agent messages only). */
  skills?: string[];
  /** Tools the agent called this turn (agent messages only). */
  tools?: ChatTool[];
  /** True while tokens are still streaming into this message. */
  streaming?: boolean;
}
