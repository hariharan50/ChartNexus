/**
 * @vitest-environment node
 */
import { afterEach, describe, expect, it } from 'vitest';
import { presentAuthError } from '$contexts/identity/messages';
import { ApiError, type Problem } from '$shared/api/errors';
import { API_UNREACHABLE, loader } from '../../app/routes/terminal/layout';

/**
 * When the API is down, every signed-in page used to fail as a bare
 * "500 · Something went wrong" (the terminal frame's `/auth/me` fetch threw),
 * and sign-in said "The server returned 502". Both now say what is wrong.
 */

const realFetch = globalThis.fetch;

afterEach(() => {
  globalThis.fetch = realFetch;
});

function runLoader() {
  const request = new Request('http://localhost:5173/settings/broker?broker=fyers', {
    headers: { cookie: 'cn_session=x' }
  });
  const context = { get: () => 'request-id' };
  return loader({ request, context, params: {} } as unknown as Parameters<typeof loader>[0]);
}

/** What a loader's `throw data(...)` carries; React Router renders it as an error response. */
interface ThrownData {
  type: string;
  data: unknown;
  init: { status: number };
}

function asThrownData(error: unknown): ThrownData {
  expect(error).toMatchObject({ type: 'DataWithResponseInit' });
  return error as ThrownData;
}

function problem(code: string, status: number): Problem {
  return { type: 'about:blank', title: code, status, detail: code, code };
}

async function thrown(promise: Promise<unknown>): Promise<unknown> {
  try {
    await promise;
  } catch (error) {
    return error;
  }
  throw new Error('expected the loader to throw');
}

describe('the terminal frame when the API is unreachable', () => {
  it('turns a failed fetch into a 503, not a 500', async () => {
    globalThis.fetch = (() => Promise.reject(new TypeError('fetch failed'))) as typeof fetch;

    const error = await thrown(runLoader());

    const response = asThrownData(error);
    expect(response.init.status).toBe(503);
    expect(response.data).toBe(API_UNREACHABLE);
  });

  it('treats a gateway 502 the same way', async () => {
    globalThis.fetch = (() =>
      Promise.resolve(new Response('Bad Gateway', { status: 502 }))) as typeof fetch;

    const error = await thrown(runLoader());

    expect(asThrownData(error).init.status).toBe(503);
  });

  it('still sends a signed-out visitor to sign in', async () => {
    globalThis.fetch = (() =>
      Promise.resolve(
        new Response(JSON.stringify({ code: 'unauthenticated', detail: 'no' }), {
          status: 401,
          headers: { 'content-type': 'application/json' }
        })
      )) as typeof fetch;

    const error = await thrown(runLoader());

    expect(error).toBeInstanceOf(Response);
    expect((error as Response).status).toBe(303);
    expect((error as Response).headers.get('location')).toBe(
      '/login?next=%2Fsettings%2Fbroker%3Fbroker%3Dfyers'
    );
  });
});

describe('sign-in messages when the API is unreachable', () => {
  it.each([502, 503, 504])('a %i says the server cannot be reached', (status) => {
    const presented = presentAuthError(new ApiError(problem('http_error', status), status));
    expect(presented.message).toMatch(/Can't reach the ChartNexus server/);
  });

  it('a network failure says the same kind of thing', () => {
    expect(presentAuthError(new TypeError('fetch failed')).message).toMatch(/reach the server/);
  });

  it('an unhandled 500 never shows the raw exception text', () => {
    const raw =
      "Error Multiple exceptions: [Errno 10061] Connect call failed ('127.0.0.1', 6381) connecting to localhost:6381.";
    const presented = presentAuthError(
      new ApiError({ ...problem('internal_error', 500), detail: raw, request_id: 'req-123' }, 500)
    );
    expect(presented.message).toBe(
      'Something went wrong on our side. Please try again in a moment. (reference req-123)'
    );
    expect(presented.message).not.toMatch(/6381|Errno/);
  });

  it('wrong credentials are unaffected', () => {
    const presented = presentAuthError(new ApiError(problem('invalid_credentials', 401), 401));
    expect(presented.message).toBe('Those sign-in details do not match an account.');
  });
});
