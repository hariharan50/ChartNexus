/**
 * The request-scoped `fetch` a loader hands to `apiFetch`.
 *
 * This is the replacement for SvelteKit's `event.fetch` plus the `handleFetch`
 * hook, which together did three things for free that Node's global `fetch`
 * does not:
 *
 *   1. Resolved a same-origin path. `apiFetch` builds `/api/v1/...`, which the
 *      browser resolves against the page origin. A loader has no page origin,
 *      and must not loop the request back through this Node process anyway.
 *   2. Forwarded the browser's `Cookie` header. `credentials: 'include'` is a
 *      browser concept; server-side it does nothing, so the session cookie has
 *      to be copied across explicitly.
 *   3. Forwarded `x-request-id`, so the API's logs join up with the SSR render
 *      that called it.
 */
export function createServerFetch(request: Request, requestId: string): typeof fetch {
  const cookie = request.headers.get('cookie') ?? '';
  const base = process.env.API_INTERNAL_URL ?? 'http://localhost:8000';

  return async (input, init) => {
    const raw = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
    const url = raw.startsWith('/') ? new URL(raw, base) : new URL(raw);

    const headers = new Headers(init?.headers);
    if (cookie) headers.set('cookie', cookie);
    headers.set('x-request-id', requestId);

    // A 3xx from the API is data, not something to chase: the loader decides
    // what to do with it rather than silently following it server-side.
    return fetch(url, { ...init, headers, redirect: 'manual' });
  };
}
