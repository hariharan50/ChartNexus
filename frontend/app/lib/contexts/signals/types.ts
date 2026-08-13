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
