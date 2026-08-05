import { ApiError, parseProblem } from './errors';

/**
 * The single fetch used by every endpoint (wired in orval.config.ts).
 *
 * Requests go to a same-origin `/api` path so the httpOnly session cookie is
 * sent without loosening SameSite; the Vite dev server proxies that path to the
 * backend, and production serves both behind one hostname.
 */

const API_PREFIX = '/api/v1';
const CSRF_COOKIE = 'mc_csrf';
const CSRF_HEADER = 'X-CSRF-Token';
const UNSAFE_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);
const REFRESH_PATH = '/api/v1/auth/refresh';

// Endpoints that establish or re-establish a session themselves. A 401 from
// one of these is the real answer (bad credentials, an already-invalid
// refresh token, an expired OAuth code) — retrying it after another refresh
// attempt would just recurse or paper over a genuine auth failure.
const AUTH_FLOW_PATHS = new Set([
  '/api/v1/auth/login',
  '/api/v1/auth/register',
  '/api/v1/auth/refresh',
  '/api/v1/auth/google/authorize',
  '/api/v1/auth/google/callback'
]);

// The access-token cookie lives 15 minutes (see backend Settings.auth); the
// refresh-token cookie lives 30 days. Every other endpoint's 401 most likely
// just means the access token aged out under a still-open session, so a
// silent refresh-and-retry keeps the user working instead of bouncing them to
// `/login` every 15 minutes. Concurrent 401s share one refresh call.
let refreshInFlight: Promise<boolean> | null = null;

async function refreshSession(fetcher: typeof fetch): Promise<boolean> {
  refreshInFlight ??= fetcher(REFRESH_PATH, {
    method: 'POST',
    headers: { 'content-type': 'application/json', accept: 'application/json' },
    body: '{}',
    credentials: 'include'
  })
    .then((res) => res.ok)
    .catch(() => false)
    .finally(() => {
      refreshInFlight = null;
    });
  return refreshInFlight;
}

export interface ApiFetchOptions extends RequestInit {
  url: string;
  params?: Record<string, string | number | boolean | undefined | null>;
  /** SvelteKit's `fetch`, when called from a `load` function. */
  fetcher?: typeof fetch | undefined;
}

export async function apiFetch<T>({ url, params, fetcher, ...init }: ApiFetchOptions): Promise<T> {
  const target = buildUrl(url, params);
  const method = (init.method ?? 'GET').toUpperCase();
  const doFetch = fetcher ?? fetch;

  const headers = new Headers(init.headers);
  if (init.body !== undefined && !headers.has('content-type')) {
    headers.set('content-type', 'application/json');
  }
  headers.set('accept', 'application/json');

  // The API authenticates the browser from an httpOnly cookie, so every
  // state-changing call has to prove it was issued by our own page. The CSRF
  // cookie is readable by design; a cross-site form cannot copy it into a header.
  if (UNSAFE_METHODS.has(method)) {
    const token = readCookie(CSRF_COOKIE);
    if (token) headers.set(CSRF_HEADER, token);
  }

  let response = await doFetch(target, {
    ...init,
    headers,
    // Required for the session cookie; the API rejects cross-origin credentials
    // it did not issue.
    credentials: 'include'
  });

  if (response.status === 401 && !AUTH_FLOW_PATHS.has(target)) {
    const refreshed = await refreshSession(doFetch);
    if (refreshed) {
      // The refresh rotates the CSRF cookie along with the session, so a
      // retried mutation must read it again rather than reuse the stale header.
      if (UNSAFE_METHODS.has(method)) {
        const token = readCookie(CSRF_COOKIE);
        if (token) headers.set(CSRF_HEADER, token);
      }
      response = await doFetch(target, { ...init, headers, credentials: 'include' });
    }
  }

  if (!response.ok) {
    throw new ApiError(await parseProblem(response), response.status);
  }

  // Detect an empty body from the payload itself rather than the
  // `content-length` header: during SSR that header is not exposed unless it is
  // whitelisted in `filterSerializedResponseHeaders`, and reading it there
  // throws. A 204 or an empty string both mean "no content".
  if (response.status === 204) {
    return undefined as T;
  }

  const text = await response.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

function readCookie(name: string): string | null {
  if (typeof document === 'undefined') return null;
  const match = document.cookie.match(
    new RegExp(`(?:^|;\\s*)${name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}=([^;]*)`)
  );
  return match?.[1] ? decodeURIComponent(match[1]) : null;
}

function buildUrl(url: string, params?: ApiFetchOptions['params']): string {
  const path = url.startsWith('/api')
    ? url
    : `${API_PREFIX}${url.startsWith('/') ? url : `/${url}`}`;
  if (!params) return path;

  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null) query.append(key, String(value));
  }
  const serialised = query.toString();
  return serialised ? `${path}?${serialised}` : path;
}

export default apiFetch;
