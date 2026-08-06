import { createReadableStreamFromReadable } from '@react-router/node';
import { isbot } from 'isbot';
import { PassThrough } from 'node:stream';
import { renderToPipeableStream } from 'react-dom/server';
import {
  ServerRouter,
  type EntryContext,
  type HandleErrorFunction,
  type RouterContextProvider
} from 'react-router';
import { nonceContext, requestIdContext } from './middleware/context';

const ABORT_DELAY = 5_000;

export default function handleRequest(
  request: Request,
  responseStatusCode: number,
  responseHeaders: Headers,
  routerContext: EntryContext,
  loadContext: Readonly<RouterContextProvider>
): Promise<Response> {
  // `<ServerRouter nonce>` is the default for every nonce-aware component it
  // renders — <Links>, <Scripts>, <ScrollRestoration> — so the CSP nonce set in
  // middleware only has to be handed over once, here.
  const nonce = loadContext.get(nonceContext);

  return new Promise((resolve, reject) => {
    let shellRendered = false;

    // Crawlers get the fully-buffered document (`onAllReady`); browsers get the
    // shell as soon as it is ready (`onShellReady`).
    const readyOption = isbot(request.headers.get('user-agent') ?? '')
      ? 'onAllReady'
      : 'onShellReady';

    const { pipe, abort } = renderToPipeableStream(
      <ServerRouter context={routerContext} url={request.url} nonce={nonce} />,
      {
        nonce,
        [readyOption]() {
          shellRendered = true;
          const body = new PassThrough();
          const stream = createReadableStreamFromReadable(body);

          responseHeaders.set('Content-Type', 'text/html');
          resolve(
            new Response(stream, {
              headers: responseHeaders,
              status: responseStatusCode
            })
          );
          pipe(body);
        },
        onShellError(error: unknown) {
          reject(error instanceof Error ? error : new Error(String(error)));
        },
        onError(error: unknown) {
          responseStatusCode = 500;
          // Errors thrown before the shell flushed are already surfaced through
          // onShellError; logging them twice just doubles the noise.
          if (shellRendered) {
            console.error(error);
          }
        }
      }
    );

    setTimeout(abort, ABORT_DELAY);
  });
}

/**
 * Replaces `hooks.server.ts`'s `handleServerError`. Logging only — the shape
 * the error boundary renders is decided in root.tsx.
 */
export const handleError: HandleErrorFunction = (error, { request, context }) => {
  // A client that navigated away mid-render is not an error worth logging.
  if (request.signal.aborted) return;

  const requestId = context.get(requestIdContext);
  console.error('[ssr]', requestId, error);
};
