/**
 * Hand-written types mirroring the backend `signals` and `copilot` schemas.
 *
 * The OpenAPI contract is empty and orval has never run, so — like the other
 * contexts — these are maintained by hand alongside the Pydantic responses.
 */

import type { DataSourceName } from '$contexts/broker-connections/types';

export type Decision = 'BUY' | 'SELL' | 'HOLD';

export interface SkillRead {
  skill: string;
  label: string;
  weight: number;
  /** `null` when the skill had no usable data this session. */
  score: number | null;
  headline: string;
  details: string[];
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

export interface Scaffold {
  entry: number | null;
  stop: number | null;
  target: number | null;
  risk_reward: number | null;
  suggested_contract: string | null;
}

export interface Guidance {
  symbol: string;
  decision: Decision;
  confidence: number;
  score: number;
  provenance: DataSourceName;
  is_actionable: boolean;
  rationale: string;
  expiry_ref: string | null;
  warnings: string[];
  skills: SkillRead[];
  levels: Levels;
  scaffold: Scaffold;
}

export interface AskResponse {
  answer: string;
  symbol: string;
  decision: string;
  provenance: DataSourceName;
  /** Which provider produced the text: "rule_based" when keyless, else the LLM. */
  source: string;
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

/** A rendered chat turn in the console. */
export interface ChatMessage {
  id: string;
  role: 'user' | 'agent';
  text: string;
  source?: string;
}
