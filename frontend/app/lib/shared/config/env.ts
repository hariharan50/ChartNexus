/**
 * Browser-visible configuration.
 *
 * Only `PUBLIC_`-prefixed variables are inlined into the bundle (`envPrefix` in
 * vite.config.ts) — the same contract SvelteKit's `env.publicPrefix` enforced.
 * Containing the `import.meta.env` access here keeps the rest of the app from
 * depending on the bundler's env shape, which is what `$env/static/public` did.
 */

const env = import.meta.env as Record<string, string | undefined>;

/** Same-origin API path; the dev server proxies it to the backend. */
export const PUBLIC_API_BASE_URL = env.PUBLIC_API_BASE_URL ?? '/api/v1';

/**
 * Websocket path for the realtime stream.
 *
 * Same-origin by default: the Vite dev server proxies `/ws` to port 8001 and
 * nginx does the same in production, which keeps the connection on one origin.
 * An absolute `ws://host/ws` is also honoured — `compose.dev.yml` sets one for
 * the containerised frontend. `resolveWebsocketUrl` handles both.
 */
export const PUBLIC_WS_URL = env.PUBLIC_WS_URL ?? '/ws';

export const PUBLIC_ENVIRONMENT = env.PUBLIC_ENVIRONMENT ?? 'local';
