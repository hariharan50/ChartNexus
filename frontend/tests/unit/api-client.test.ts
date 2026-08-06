import { beforeEach, describe, expect, it } from 'vitest';
import { apiFetch } from '$shared/api/client';
import { ApiError } from '$shared/api/errors';

/**
 * `client.ts` carries the auth behaviour the whole app depends on — CSRF,
 * the silent 401 refresh, problem-details parsing — and had no tests before the
 * React port. These pin it down.
 *
 * A recording `fetcher` stub stands in for the network. `apiFetch` routes every
 * call, including the refresh and the retry, through that same argument, so the
 * stub sees the complete request sequence.
 */

interface Call {
  url: string;
  init: RequestInit;
  headers: Headers;
}

function recorder(responses: Array<() => Response>) {
  const calls: Call[] = [];
  let index = 0;

  const fetcher = ((url: string | URL | Request, init?: RequestInit) => {
    calls.push({
      url: String(url),
      init: init ?? {},
      headers: new Headers(init?.headers)
    });
    const next = responses[Math.min(index, responses.length - 1)];
    index += 1;
    return Promise.resolve(next!());
  }) as typeof fetch;

  return { fetcher, calls };
}

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' }
  });

const problem = (status: number, body: Record<string, unknown>) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/problem+json' }
  });

beforeEach(() => {
  document.cookie = 'mc_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/';
});

describe('url building', () => {
  it('prefixes a bare path with /api/v1', async () => {
    const { fetcher, calls } = recorder([() => json({ ok: true })]);
    await apiFetch({ url: '/auth/me', fetcher });
    expect(calls[0]?.url).toBe('/api/v1/auth/me');
  });

  it('accepts a path without a leading slash', async () => {
    const { fetcher, calls } = recorder([() => json({ ok: true })]);
    await apiFetch({ url: 'auth/me', fetcher });
    expect(calls[0]?.url).toBe('/api/v1/auth/me');
  });

  it('leaves an already-prefixed /api path alone', async () => {
    const { fetcher, calls } = recorder([() => json({ ok: true })]);
    await apiFetch({ url: '/api/v1/auth/me', fetcher });
    expect(calls[0]?.url).toBe('/api/v1/auth/me');
  });

  it('serialises params and drops null and undefined', async () => {
    const { fetcher, calls } = recorder([() => json({ ok: true })]);
    await apiFetch({
      url: '/market/option-chain',
      params: { symbol: 'NIFTY', expiry: undefined, strike: 0, live: false, cursor: null },
      fetcher
    });
    expect(calls[0]?.url).toBe('/api/v1/market/option-chain?symbol=NIFTY&strike=0&live=false');
  });

  it('omits the query string when every param is empty', async () => {
    const { fetcher, calls } = recorder([() => json({ ok: true })]);
    await apiFetch({ url: '/spot', params: { symbol: undefined }, fetcher });
    expect(calls[0]?.url).toBe('/api/v1/spot');
  });
});

describe('headers', () => {
  it('always asks for json and defaults content-type when a body is sent', async () => {
    const { fetcher, calls } = recorder([() => json({ ok: true })]);
    await apiFetch({ url: '/auth/login', method: 'POST', body: '{}', fetcher });
    expect(calls[0]?.headers.get('accept')).toBe('application/json');
    expect(calls[0]?.headers.get('content-type')).toBe('application/json');
  });

  it('does not invent a content-type for a bodyless request', async () => {
    const { fetcher, calls } = recorder([() => json({ ok: true })]);
    await apiFetch({ url: '/auth/me', fetcher });
    expect(calls[0]?.headers.has('content-type')).toBe(false);
  });

  it('sends the CSRF token on an unsafe method', async () => {
    document.cookie = 'mc_csrf=token-abc; path=/';
    const { fetcher, calls } = recorder([() => json({ ok: true })]);
    await apiFetch({ url: '/auth/logout', method: 'POST', body: '{}', fetcher });
    expect(calls[0]?.headers.get('X-CSRF-Token')).toBe('token-abc');
  });

  it('does not send the CSRF token on a read', async () => {
    document.cookie = 'mc_csrf=token-abc; path=/';
    const { fetcher, calls } = recorder([() => json({ ok: true })]);
    await apiFetch({ url: '/auth/me', fetcher });
    expect(calls[0]?.headers.has('X-CSRF-Token')).toBe(false);
  });

  it('omits the CSRF header entirely when no cookie is set', async () => {
    const { fetcher, calls } = recorder([() => json({ ok: true })]);
    await apiFetch({ url: '/auth/logout', method: 'POST', body: '{}', fetcher });
    expect(calls[0]?.headers.has('X-CSRF-Token')).toBe(false);
  });

  it('sends credentials so the httpOnly session cookie travels', async () => {
    const { fetcher, calls } = recorder([() => json({ ok: true })]);
    await apiFetch({ url: '/auth/me', fetcher });
    expect(calls[0]?.init.credentials).toBe('include');
  });
});

describe('401 refresh', () => {
  it('refreshes once and retries the original request', async () => {
    const { fetcher, calls } = recorder([
      () => problem(401, { code: 'session_expired' }),
      () => json({ ok: true }), // the refresh
      () => json({ id: 'u1' }) // the retry
    ]);

    const result = await apiFetch<{ id: string }>({ url: '/auth/me', fetcher });

    expect(result).toEqual({ id: 'u1' });
    expect(calls.map((c) => c.url)).toEqual([
      '/api/v1/auth/me',
      '/api/v1/auth/refresh',
      '/api/v1/auth/me'
    ]);
  });

  it('re-reads the CSRF cookie before retrying, because refresh rotates it', async () => {
    document.cookie = 'mc_csrf=stale; path=/';

    const { fetcher, calls } = recorder([
      () => problem(401, { code: 'session_expired' }),
      () => {
        document.cookie = 'mc_csrf=rotated; path=/';
        return json({ ok: true });
      },
      () => json({ ok: true })
    ]);

    await apiFetch({ url: '/broker/connect', method: 'POST', body: '{}', fetcher });

    expect(calls[0]?.headers.get('X-CSRF-Token')).toBe('stale');
    expect(calls[2]?.headers.get('X-CSRF-Token')).toBe('rotated');
  });

  it('does not refresh when an auth-flow endpoint returns 401', async () => {
    const { fetcher, calls } = recorder([() => problem(401, { code: 'invalid_credentials' })]);

    await expect(
      apiFetch({ url: '/auth/login', method: 'POST', body: '{}', fetcher })
    ).rejects.toBeInstanceOf(ApiError);

    expect(calls).toHaveLength(1);
  });

  it('surfaces the original 401 when the refresh itself fails', async () => {
    const { fetcher, calls } = recorder([
      () => problem(401, { code: 'session_expired' }),
      () => problem(401, { code: 'session_revoked' })
    ]);

    await expect(apiFetch({ url: '/auth/me', fetcher })).rejects.toMatchObject({ status: 401 });
    expect(calls).toHaveLength(2);
  });

  it('shares one refresh call between concurrent 401s', async () => {
    let refreshCount = 0;
    const calls: string[] = [];

    const fetcher = ((url: string | URL) => {
      const target = String(url);
      calls.push(target);
      if (target === '/api/v1/auth/refresh') {
        refreshCount += 1;
        return Promise.resolve(json({ ok: true }));
      }
      // Every non-refresh call 401s the first time it is seen.
      const firstAttempt = calls.filter((c) => c === target).length === 1;
      return Promise.resolve(firstAttempt ? problem(401, { code: 'x' }) : json({ ok: true }));
    }) as typeof fetch;

    await Promise.all([
      apiFetch({ url: '/spot', fetcher }),
      apiFetch({ url: '/futures', fetcher }),
      apiFetch({ url: '/market-status', fetcher })
    ]);

    expect(refreshCount).toBe(1);
  });
});

describe('response handling', () => {
  it('returns undefined for 204', async () => {
    const { fetcher } = recorder([() => new Response(null, { status: 204 })]);
    await expect(apiFetch({ url: '/thing', method: 'DELETE', fetcher })).resolves.toBeUndefined();
  });

  it('returns undefined for an empty 200 body', async () => {
    const { fetcher } = recorder([() => new Response('', { status: 200 })]);
    await expect(apiFetch({ url: '/thing', fetcher })).resolves.toBeUndefined();
  });

  it('throws a typed ApiError carrying the problem document', async () => {
    const { fetcher } = recorder([
      () =>
        problem(422, {
          title: 'Validation failed',
          code: 'validation_error',
          detail: 'phone is invalid',
          request_id: 'req-42',
          errors: [{ field: 'phone', reason: 'must be an Indian mobile number' }]
        })
    ]);

    const error = await apiFetch({ url: '/auth/register', method: 'POST', body: '{}', fetcher })
      .then(() => null)
      .catch((e: unknown) => e);

    expect(error).toBeInstanceOf(ApiError);
    const apiError = error as ApiError;
    expect(apiError.status).toBe(422);
    expect(apiError.code).toBe('validation_error');
    expect(apiError.requestId).toBe('req-42');
    expect(apiError.fieldErrors).toEqual({ phone: 'must be an Indian mobile number' });
    // 4xx that is neither 401 nor 429: the server refused, so react-query
    // must not retry it.
    expect(apiError.isTerminal).toBe(true);
  });

  it('treats 429 and 5xx as retryable', async () => {
    for (const status of [429, 500, 503]) {
      const { fetcher } = recorder([() => problem(status, { code: 'x' })]);
      const error = (await apiFetch({ url: '/spot', fetcher }).catch(
        (e: unknown) => e
      )) as ApiError;
      expect(error.isTerminal).toBe(false);
    }
  });

  it('survives a non-json error body from a proxy', async () => {
    const { fetcher } = recorder([
      () => new Response('<html>502 Bad Gateway</html>', { status: 502 })
    ]);
    const error = (await apiFetch({ url: '/spot', fetcher }).catch((e: unknown) => e)) as ApiError;
    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(502);
  });
});
