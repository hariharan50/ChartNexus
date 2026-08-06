import type { MiddlewareFunction } from 'react-router';
import { requestIdContext } from './context';

export const REQUEST_ID_HEADER = 'x-request-id';

/**
 * Adopts an inbound `x-request-id` or mints one, publishes it to the request
 * context, and echoes it on the response.
 *
 * This is `hooks.server.ts`'s `handle` — the id ties an SSR render to the API
 * calls it made and to the backend's logs for the same request. The forwarding
 * half (attaching it to outgoing API calls) lives in
 * app/lib/shared/api/server-fetch.ts, which is what `handleFetch` used to do.
 */
export const requestIdMiddleware: MiddlewareFunction<Response> = async (
  { request, context },
  next
) => {
  const requestId = request.headers.get(REQUEST_ID_HEADER) ?? crypto.randomUUID();
  context.set(requestIdContext, requestId);

  const response = await next();
  response.headers.set(REQUEST_ID_HEADER, requestId);
  return response;
};
