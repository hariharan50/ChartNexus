import type { MiddlewareFunction } from 'react-router';
import { nonceContext } from './context';

/**
 * Content-Security-Policy, previously `kit.csp` in svelte.config.js.
 *
 * The directives are unchanged from the SvelteKit config; the nonce is new and
 * is not optional. SvelteKit's `csp: { mode: 'auto' }` hashed its own inline
 * hydration script for us. React Router emits two inline scripts of its own —
 * scroll restoration and `window.__reactRouterContext` — so under a bare
 * `script-src 'self'` the app renders and then never hydrates.
 */
function buildCsp(nonce: string): string {
  const scriptSrc = import.meta.env.DEV
    ? // Vite's dev client and the React Fast Refresh preamble are inline and
      // eval-based. A nonce would *disable* 'unsafe-inline' (CSP3), so dev opts
      // out of nonce-based script policy entirely. Production below is strict,
      // and Playwright runs against the production build for exactly this reason.
      ["'self'", "'unsafe-inline'", "'unsafe-eval'"]
    : ["'self'", `'nonce-${nonce}'`];

  const directives: Record<string, string[]> = {
    'default-src': ["'self'"],
    'script-src': scriptSrc,
    'style-src': ["'self'", "'unsafe-inline'"],
    'img-src': ["'self'", 'data:'],
    'connect-src': ["'self'", 'ws:', 'wss:'],
    'frame-ancestors': ["'none'"],
    'base-uri': ["'self'"],
    'form-action': ["'self'"]
  };

  return Object.entries(directives)
    .map(([name, values]) => `${name} ${values.join(' ')}`)
    .join('; ');
}

export const securityHeadersMiddleware: MiddlewareFunction<Response> = async (
  { context },
  next
) => {
  // Empty in development, where `script-src` opts out of nonces entirely (see
  // above). Emitting one anyway would be worse than useless: the browser blanks
  // a `nonce` attribute once it has read it, so every nonce-carrying element
  // React rendered on the server mismatches what it finds in the DOM at
  // hydration — including React Router's own dev-only critical-CSS <link>.
  //
  // Base64url alphabet only, so it never needs escaping inside the header.
  const nonce = import.meta.env.DEV ? '' : crypto.randomUUID().replaceAll('-', '');
  context.set(nonceContext, nonce);

  const response = await next();
  response.headers.set('Content-Security-Policy', buildCsp(nonce));
  return response;
};
