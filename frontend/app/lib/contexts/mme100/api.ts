import { apiFetch } from '$shared/api/client';
import type {
  Mme100Availability,
  Mme100Briefing,
  Mme100Enrollment,
  Mme100StreamEvent
} from './types';

/** MME100 — "Market Made Easy 100%", the Indian pre-market analyst. */

/** Whether the caller has an LLM key — the MME100 tab is disabled when not. */
export function getMme100Availability(fetcher?: typeof fetch): Promise<Mme100Availability> {
  return apiFetch<Mme100Availability>({ url: '/mme100/availability', fetcher });
}

/** Whether the autonomous pre-market briefing is on for this tenant (off by default). */
export function getMme100Enrollment(fetcher?: typeof fetch): Promise<Mme100Enrollment> {
  return apiFetch<Mme100Enrollment>({ url: '/mme100/enrollment', fetcher });
}

/** Turn the morning briefing on or off for this tenant. Persisted server-side. */
export function setMme100Enrollment(enabled: boolean): Promise<Mme100Enrollment> {
  return apiFetch<Mme100Enrollment>({
    url: '/mme100/enrollment',
    method: 'PUT',
    body: JSON.stringify({ enabled })
  });
}

/** Today's stored pre-market briefing, or `null` when none has been generated yet. */
export async function getMme100BriefingToday(
  fetcher?: typeof fetch
): Promise<Mme100Briefing | null> {
  // The endpoint answers 204 when there is no briefing yet; apiFetch maps that to
  // `undefined`, which we normalise to `null` for the query cache.
  const result = await apiFetch<Mme100Briefing | undefined>({
    url: '/mme100/briefing/today',
    fetcher
  });
  return result ?? null;
}

const STREAM_PATH = (symbol: string) => `/api/v1/mme100/${encodeURIComponent(symbol)}/ask/stream`;
const CSRF_COOKIE = 'mc_csrf';
const CSRF_HEADER = 'X-CSRF-Token';
const REFRESH_PATH = '/api/v1/auth/refresh';

/**
 * POST a question to MME100 and drive its SSE stream, invoking `onEvent` per frame.
 * Uses fetch + a reader (not EventSource) so the CSRF header and session cookie
 * travel with the POST; a single silent refresh-and-retry mirrors `apiFetch`.
 */
export async function streamMme100(
  symbol: string,
  question: string,
  sessionId: string | null,
  onEvent: (event: Mme100StreamEvent) => void,
  signal?: AbortSignal
): Promise<void> {
  const body = JSON.stringify({ question, session_id: sessionId });

  let response = await postStream(STREAM_PATH(symbol), body, signal);
  if (response.status === 401) {
    const refreshed = await refreshOnce();
    if (refreshed) response = await postStream(STREAM_PATH(symbol), body, signal);
  }
  if (!response.ok || !response.body) {
    throw new Error(`MME100 stream failed (${response.status})`);
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
          onEvent(JSON.parse(payload) as Mme100StreamEvent);
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
