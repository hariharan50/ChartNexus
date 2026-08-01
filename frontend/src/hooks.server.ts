import type { Handle, HandleFetch, HandleServerError } from '@sveltejs/kit';

const REQUEST_ID_HEADER = 'x-request-id';

/**
 * Every server-rendered request carries a request id, and the same id is
 * forwarded to the API so one identifier ties together the SSR log line, the
 * API log line, and whatever the user reports.
 */
export const handle: Handle = async ({ event, resolve }) => {
  const requestId = event.request.headers.get(REQUEST_ID_HEADER) ?? crypto.randomUUID();
  event.locals.requestId = requestId;

  const response = await resolve(event, {
    filterSerializedResponseHeaders: (name) => name === 'content-type'
  });
  response.headers.set(REQUEST_ID_HEADER, requestId);
  return response;
};

/** Forward cookies and the correlation id on server-side calls to the API. */
export const handleFetch: HandleFetch = async ({ event, request, fetch }) => {
  const apiOrigin = new URL(request.url).origin;
  if (apiOrigin === event.url.origin || request.url.startsWith('/api')) {
    request.headers.set('cookie', event.request.headers.get('cookie') ?? '');
    request.headers.set(REQUEST_ID_HEADER, event.locals.requestId);
  }
  return fetch(request);
};

export const handleServerError: HandleServerError = ({ error, event, status, message }) => {
  console.error('[ssr]', event.locals.requestId, status, error);
  const detail = status < 500 ? message : 'An unexpected error occurred.';
  return {
    message: detail,
    code: status === 404 ? 'not_found' : 'internal_error',
    detail,
    requestId: event.locals.requestId
  };
};
