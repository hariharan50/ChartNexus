import { apiFetch } from '$shared/api/client';
import type {
  HuginAvailability,
  HuginCall,
  HuginCalls,
  HuginEnrollment,
  HuginHistory,
  HuginMemoryToday
} from './types';

/** HUGIN — the desk's autonomous market memory (read-only). */

/** Whether the caller has an LLM key — the HUGIN tab is disabled when not. */
export function getHuginAvailability(fetcher?: typeof fetch): Promise<HuginAvailability> {
  return apiFetch<HuginAvailability>({ url: '/hugin/availability', fetcher });
}

/** Whether HUGIN is turned on for this tenant (off by default). */
export function getHuginEnrollment(fetcher?: typeof fetch): Promise<HuginEnrollment> {
  return apiFetch<HuginEnrollment>({ url: '/hugin/enrollment', fetcher });
}

/** Turn HUGIN on or off for this tenant. Persisted server-side. */
export function setHuginEnrollment(enabled: boolean): Promise<HuginEnrollment> {
  return apiFetch<HuginEnrollment>({
    url: '/hugin/enrollment',
    method: 'PUT',
    body: JSON.stringify({ enabled })
  });
}

/** Today's hourly observations (with grades), active lessons, and the hit-rate. */
export function getHuginMemoryToday(
  symbol: string,
  fetcher?: typeof fetch
): Promise<HuginMemoryToday> {
  return apiFetch<HuginMemoryToday>({ url: `/hugin/${symbol}/memory/today`, fetcher });
}

/** HUGIN's multi-day track record — per-day hit-rate and the overall trend. */
export function getHuginHistory(
  symbol: string,
  days = 7,
  fetcher?: typeof fetch
): Promise<HuginHistory> {
  return apiFetch<HuginHistory>({ url: `/hugin/${symbol}/history`, params: { days }, fetcher });
}

/** Recent memory-driven calls HUGIN has saved. */
export function getHuginCalls(symbol: string, fetcher?: typeof fetch): Promise<HuginCalls> {
  return apiFetch<HuginCalls>({ url: `/hugin/${symbol}/calls`, fetcher });
}

/** Generate and save a new memory-driven call. */
export function generateHuginCall(symbol: string): Promise<HuginCall> {
  return apiFetch<HuginCall>({ url: `/hugin/${symbol}/call`, method: 'POST', body: '{}' });
}

/** One frame off HUGIN's chat SSE stream (memory-grounded; no tool events). */
export type HuginChatEvent =
  | { type: 'session'; session_id: string }
  | { type: 'token'; text: string }
  | { type: 'done' }
  | { type: 'error'; message: string };

const CHAT_PATH = (symbol: string) => `/api/v1/hugin/${encodeURIComponent(symbol)}/ask/stream`;
const CSRF_COOKIE = 'mc_csrf';
const CSRF_HEADER = 'X-CSRF-Token';
const REFRESH_PATH = '/api/v1/auth/refresh';

/**
 * POST a question to HUGIN and drive its SSE stream, invoking `onEvent` per frame.
 * Uses fetch + a reader (not EventSource) so the CSRF header and session cookie
 * travel with the POST; a single silent refresh-and-retry mirrors `apiFetch`.
 */
export async function streamHuginChat(
  symbol: string,
  question: string,
  sessionId: string | null,
  onEvent: (event: HuginChatEvent) => void,
  signal?: AbortSignal
): Promise<void> {
  const body = JSON.stringify({ question, session_id: sessionId });

  let response = await postStream(CHAT_PATH(symbol), body, signal);
  if (response.status === 401) {
    const refreshed = await refreshOnce();
    if (refreshed) response = await postStream(CHAT_PATH(symbol), body, signal);
  }
  if (!response.ok || !response.body) {
    throw new Error(`HUGIN chat stream failed (${response.status})`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
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
          onEvent(JSON.parse(payload) as HuginChatEvent);
        } catch {
          // A malformed frame is not worth killing the turn — skip it.
        }
      }
      boundary = buffer.indexOf('\n\n');
    }
  }
}

function postStream(path: string, body: string, signal?: AbortSignal): Promise<Response> {
  const headers = new Headers({
    'content-type': 'application/json',
    accept: 'text/event-stream'
  });
  const token = readCookie(CSRF_COOKIE);
  if (token) headers.set(CSRF_HEADER, token);
  const init: RequestInit = { method: 'POST', headers, body, credentials: 'include' };
  if (signal) init.signal = signal;
  return fetch(path, init);
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
