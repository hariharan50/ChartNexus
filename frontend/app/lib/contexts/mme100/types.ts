/** Wire types for MME100 — the "Market Made Easy 100%" pre-market analyst. */

export type Mme100Availability = {
  available: boolean;
};

export type Mme100Enrollment = {
  enabled: boolean;
};

/** Today's stored pre-market briefing (the autonomous morning run). */
export type Mme100Briefing = {
  trading_day: string;
  instruments: string[];
  markdown: string;
  source: string;
  created_at: string | null;
};

/**
 * One frame off MME100's SSE stream. Same shape as HELLA's `AgentStreamEvent`:
 * `session` threads follow-ups, `skills` lists the six analysis sections, `token`
 * chunks build the answer, `tool` events say what it is reading (market tools and
 * web search), `done`/`error` close the turn.
 */
export type Mme100StreamEvent =
  | { type: 'session'; session_id: string }
  | { type: 'skills'; titles: string[] }
  | { type: 'token'; text: string }
  | { type: 'tool'; status: 'started' | 'finished'; name: string; title?: string }
  | { type: 'done' }
  | { type: 'error'; message: string };
