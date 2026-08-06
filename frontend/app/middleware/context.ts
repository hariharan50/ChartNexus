import { createContext } from 'react-router';

/**
 * Request-scoped values, the replacement for SvelteKit's `event.locals`.
 *
 * Nothing here is a singleton: a `RouterContextProvider` is created per request,
 * so a value set in middleware is visible to that request's loaders and to
 * nothing else. That request-scoping is the whole point — see the note on
 * module-scope state in app/lib/shared/api/client.ts.
 */

/** Correlates an SSR render with the API calls it made. */
export const requestIdContext = createContext<string>('');

/** Per-request CSP nonce, threaded into <Scripts> so hydration is allowed. */
export const nonceContext = createContext<string>('');
