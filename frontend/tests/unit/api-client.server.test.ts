/**
 * @vitest-environment node
 */
import { afterEach, describe, expect, it } from 'vitest';
import { apiFetch } from '$shared/api/client';
import { createServerFetch } from '$shared/api/server-fetch';

/**
 * Server-side behaviour, which needs a real Node environment: `client.ts`
 * branches on `typeof document === 'undefined'`, and jsdom would hide that.
 */

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' }
  });

const realFetch = globalThis.fetch;
const realBase = process.env.API_INTERNAL_URL;

/** Replaces the global fetch `createServerFetch` delegates to, and records it. */
function captureGlobalFetch() {
  const seen: Array<{ url: string; headers: Headers }> = [];
  globalThis.fetch = ((input: string | URL | Request, init?: RequestInit) => {
    seen.push({ url: String(input), headers: new Headers(init?.headers) });
    return Promise.resolve(json({ ok: true }));
  }) as typeof fetch;
  return seen;
}

afterEach(() => {
  globalThis.fetch = realFetch;
  if (realBase === undefined) delete process.env.API_INTERNAL_URL;
  else process.env.API_INTERNAL_URL = realBase;
});

describe('apiFetch on the server', () => {
  it('does not attempt a refresh, because the promise would be shared across requests', async () => {
    const calls: string[] = [];
    const fetcher = ((url: string | URL) => {
      calls.push(String(url));
      return Promise.resolve(json({ code: 'session_expired' }, 401));
    }) as typeof fetch;

    await expect(apiFetch({ url: '/auth/me', fetcher })).rejects.toMatchObject({ status: 401 });

    // One call: the 401 is the answer. The route guard turns it into a redirect.
    expect(calls).toEqual(['/api/v1/auth/me']);
  });
});

describe('createServerFetch', () => {
  it('resolves a same-origin api path against API_INTERNAL_URL', async () => {
    process.env.API_INTERNAL_URL = 'http://api.internal:8000';
    const seen = captureGlobalFetch();

    const request = new Request('http://localhost:5273/dashboard');
    await apiFetch({ url: '/auth/me', fetcher: createServerFetch(request, 'req-1') });

    expect(seen[0]?.url).toBe('http://api.internal:8000/api/v1/auth/me');
  });

  it('forwards the browser cookie and the request id', async () => {
    const seen = captureGlobalFetch();

    const request = new Request('http://localhost:5273/dashboard', {
      headers: { cookie: 'mc_session=abc; mc_csrf=xyz' }
    });
    await apiFetch({ url: '/auth/me', fetcher: createServerFetch(request, 'req-42') });

    expect(seen[0]?.headers.get('cookie')).toBe('mc_session=abc; mc_csrf=xyz');
    expect(seen[0]?.headers.get('x-request-id')).toBe('req-42');
  });

  it('sends no cookie header when the browser sent none', async () => {
    const seen = captureGlobalFetch();

    const request = new Request('http://localhost:5273/dashboard');
    await apiFetch({ url: '/auth/me', fetcher: createServerFetch(request, 'req-2') });

    expect(seen[0]?.headers.has('cookie')).toBe(false);
  });

  it('leaves an absolute url alone', async () => {
    const seen = captureGlobalFetch();

    const request = new Request('http://localhost:5273/dashboard');
    const fetcher = createServerFetch(request, 'req-3');
    await fetcher('http://elsewhere.test/probe');

    expect(seen[0]?.url).toBe('http://elsewhere.test/probe');
  });
});
