import { apiFetch } from '$shared/api/client';
import type { AgentAvailability, AskResponse, Guidance, GuidanceHistory } from './types';

/** AI Market Guider — decision, factors, history, and the copilot chat. */

export function getGuidance(symbol: string, fetcher?: typeof fetch): Promise<Guidance> {
  return apiFetch<Guidance>({ url: `/signals/${symbol}/guidance`, fetcher });
}

export function getGuidanceHistory(
  symbol: string,
  limit = 50,
  fetcher?: typeof fetch
): Promise<GuidanceHistory> {
  return apiFetch<GuidanceHistory>({
    url: `/signals/${symbol}/history`,
    params: { limit },
    fetcher
  });
}

export function askAgent(symbol: string, question: string): Promise<AskResponse> {
  return apiFetch<AskResponse>({
    url: `/copilot/${symbol}/ask`,
    method: 'POST',
    body: JSON.stringify({ question })
  });
}

/** Whether an LLM is configured — the Agent tab is disabled when not. */
export function getAgentAvailability(fetcher?: typeof fetch): Promise<AgentAvailability> {
  return apiFetch<AgentAvailability>({ url: '/copilot/availability', fetcher });
}

/**
 * One frame off the agent's Server-Sent Events stream.
 *
 * `session` arrives first and carries the id that threads follow-ups; `token`
 * chunks build the answer; `tool` events say what Hella is doing while she
 * reasons; `done`/`error` close the turn.
 */
export type AgentStreamEvent =
  | { type: 'session'; session_id: string }
  | { type: 'skills'; titles: string[] }
  | { type: 'token'; text: string }
  | { type: 'tool'; status: 'started' | 'finished'; name: string; title?: string }
  | { type: 'done' }
  | { type: 'error'; message: string };

const STREAM_PATH = (symbol: string) => `/api/v1/copilot/${encodeURIComponent(symbol)}/ask/stream`;
const CSRF_COOKIE = 'mc_csrf';
const CSRF_HEADER = 'X-CSRF-Token';
const REFRESH_PATH = '/api/v1/auth/refresh';

/**
 * POST a question and drive the agent's SSE stream, invoking `onEvent` per
 * frame. Resolves when the stream closes; rejects only on a transport failure
 * (a model error arrives as an `error` event, not a rejection).
 *
 * Uses `fetch` + a stream reader rather than `EventSource`: the endpoint is a
 * POST that needs the CSRF header and the session cookie, neither of which
 * `EventSource` can send. A single silent refresh-and-retry mirrors `apiFetch`,
 * so a 15-minute access token aging out mid-chat doesn't drop the turn.
 */
export async function streamAgent(
  symbol: string,
  question: string,
  sessionId: string | null,
  onEvent: (event: AgentStreamEvent) => void,
  signal?: AbortSignal
): Promise<void> {
  const body = JSON.stringify({ question, session_id: sessionId });

  let response = await postStream(symbol, body, signal);
  if (response.status === 401) {
    const refreshed = await refreshOnce();
    if (refreshed) response = await postStream(symbol, body, signal);
  }
  if (!response.ok || !response.body) {
    throw new Error(`Agent stream failed (${response.status})`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  // SSE frames are separated by a blank line; a frame's payload is its `data:`
  // lines. We only emit whole frames, holding any partial tail in `buffer`.
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let boundary = buffer.indexOf('\n\n');
    while (boundary !== -1) {
      const frame = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      const payload = frame
        .split('\n')
        .filter((line) => line.startsWith('data:'))
        .map((line) => line.slice(5).trim())
        .join('');
      if (payload) {
        try {
          onEvent(JSON.parse(payload) as AgentStreamEvent);
        } catch {
          // A malformed frame is not worth killing the turn — skip it.
        }
      }
      boundary = buffer.indexOf('\n\n');
    }
  }
}

function postStream(symbol: string, body: string, signal?: AbortSignal): Promise<Response> {
  const headers = new Headers({
    'content-type': 'application/json',
    accept: 'text/event-stream'
  });
  const token = readCookie(CSRF_COOKIE);
  if (token) headers.set(CSRF_HEADER, token);
  const init: RequestInit = { method: 'POST', headers, body, credentials: 'include' };
  // Assign only when present — `exactOptionalPropertyTypes` rejects
  // `signal: undefined` against the DOM's `AbortSignal | null`.
  if (signal) init.signal = signal;
  return fetch(STREAM_PATH(symbol), init);
}

async function refreshOnce(): Promise<boolean> {
  if (typeof document === 'undefined') return false;
  try {
    const res = await fetch(REFRESH_PATH, {
      method: 'POST',
      headers: { 'content-type': 'application/json', accept: 'application/json' },
      body: '{}',
      credentials: 'include'
    });
    return res.ok;
  } catch {
    return false;
  }
}

function readCookie(name: string): string | null {
  if (typeof document === 'undefined') return null;
  const match = document.cookie.match(
    new RegExp(`(?:^|;\\s*)${name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}=([^;]*)`)
  );
  return match?.[1] ? decodeURIComponent(match[1]) : null;
}
