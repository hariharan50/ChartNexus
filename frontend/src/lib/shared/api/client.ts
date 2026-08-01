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

export interface ApiFetchOptions extends RequestInit {
  url: string;
  params?: Record<string, string | number | boolean | undefined | null>;
  /** SvelteKit's `fetch`, when called from a `load` function. */
  fetcher?: typeof fetch | undefined;
}

export async function apiFetch<T>({ url, params, fetcher, ...init }: ApiFetchOptions): Promise<T> {
  const target = buildUrl(url, params);
  const method = (init.method ?? 'GET').toUpperCase();

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

  const response = await (fetcher ?? fetch)(target, {
    ...init,
    headers,
    // Required for the session cookie; the API rejects cross-origin credentials
    // it did not issue.
    credentials: 'include'
  });

  if (!response.ok) {
    throw new ApiError(await parseProblem(response), response.status);
  }

  if (response.status === 204 || response.headers.get('content-length') === '0') {
    return undefined as T;
  }

  return (await response.json()) as T;
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
