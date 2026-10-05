import {
  isRouteErrorResponse,
  Links,
  Meta,
  Outlet,
  Scripts,
  ScrollRestoration,
  useRouteError,
  useRouteLoaderData
} from 'react-router';
import './app.css';
import { nonceContext, requestIdContext } from './middleware/context';
import { requestIdMiddleware } from './middleware/request-id';
import { securityHeadersMiddleware } from './middleware/security-headers';
import errorStyles from './root-error.module.css';
import styles from './root.module.css';
import type { Route } from './+types/root';

/**
 * Root route. Replaces `src/app.html`, `src/routes/+layout.svelte` and
 * `src/routes/+error.svelte` in one file, plus the two `hooks.server.ts`
 * responsibilities via the middleware below.
 */

// Root middleware runs for document requests and for the `.data` requests
// client navigations make, so every response carries both headers.
export const middleware: Route.MiddlewareFunction[] = [
  requestIdMiddleware,
  securityHeadersMiddleware
];

export function loader({ context }: Route.LoaderArgs) {
  return {
    // Surfaced by the error boundary so a user can quote a reference that ties
    // back to the server logs — what `App.Error.requestId` carried before.
    requestId: context.get(requestIdContext),
    // Needed by the pre-paint theme script below, which the CSP would
    // otherwise block.
    nonce: context.get(nonceContext)
  };
}

/**
 * Applies the stored theme before first paint.
 *
 * The server cannot know which theme this browser chose — the preference lives
 * in localStorage, and the document ships with `data-theme="dark"`. Without
 * this, a light-theme user saw a dark flash on every page load; that was true
 * of the SvelteKit app too (`app.html` hard-coded the attribute and ran no
 * script), so this is a fix rather than a port.
 *
 * Deliberately tiny and synchronous: it must finish before the browser paints.
 * It only writes attributes the stores already read back in their `init()`, so
 * nothing downstream needs to know it ran.
 */
const THEME_BOOTSTRAP = `try{
var t=localStorage.getItem('cn-theme');
if(t==='light'||t==='dark'||t==='midnight'||t==='warm'||t==='terminal')document.documentElement.setAttribute('data-theme',t);
var c=localStorage.getItem('cn-pref-callput');
document.documentElement.setAttribute('data-callput',c==='inverted'?'inverted':'classic');
var lp=localStorage.getItem('cn-landing-theme');
if(lp==='light')document.documentElement.setAttribute('data-lp-theme','light');
}catch(e){}`;

// `meta` owns the title in both states. The error branch is what
// `+error.svelte`'s `<svelte:head><title>` did; keeping it here rather than in
// the boundary avoids emitting two <title> elements.
export const meta: Route.MetaFunction = ({ error }) =>
  error ? [{ title: `${errorStatus(error)} · ChartNexus` }] : [{ title: 'ChartNexus' }];

export const links: Route.LinksFunction = () => [
  { rel: 'icon', href: '/favicon/favicon.svg', type: 'image/svg+xml' },
  { rel: 'manifest', href: '/manifest.webmanifest' },
  // `crossOrigin` is required even though this is same-origin: CSS font fetches
  // are always CORS-mode, so a preload without it does not match the request the
  // stylesheet makes and the font is downloaded twice.
  {
    rel: 'preload',
    href: '/fonts/inter-latin-var.woff2',
    as: 'font',
    type: 'font/woff2',
    crossOrigin: 'anonymous'
  }
];

export function Layout({ children }: { children: React.ReactNode }) {
  // Absent when the root loader itself failed, and empty in development where
  // the CSP allows inline scripts outright.
  const nonce = useRouteLoaderData<typeof loader>('root')?.nonce;

  // In production an unsigned inline script would just be blocked, so there is
  // nothing to gain by emitting one; the page falls back to the server's theme.
  const canInlineScript = import.meta.env.DEV || Boolean(nonce);

  return (
    /*
     * `data-theme` is a static literal, never React state: the theme store
     * writes the attribute imperatively on the client (as it did under Svelte),
     * so React must not reconcile it.
     *
     * `suppressHydrationWarning` is required, not cosmetic. React Router
     * hydrates the whole `document`, so `<html>` is inside the hydration root —
     * SvelteKit never had this exposure, because its `<html>` lived in
     * `app.html` outside the mounted tree. The bootstrap script below runs
     * before hydration and rewrites `data-theme`/`data-callput`, which React
     * then sees as a server/client mismatch. Suppressing it here tells React the
     * difference is deliberate and to leave the DOM's values alone — which is
     * exactly what we want, since the browser's stored preference should win.
     * It applies only to this element's own attributes, not to any descendant.
     */
    <html lang="en" data-theme="dark" suppressHydrationWarning>
      <head>
        <meta charSet="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <meta name="color-scheme" content="dark light" />
        <meta name="theme-color" content="#0b0e14" />
        <Meta />
        <Links />
        {canInlineScript ? (
          // Browsers blank a `nonce` content attribute once they have read it,
          // so what React rendered never matches what it finds in the DOM.
          <script
            nonce={nonce || undefined}
            suppressHydrationWarning
            dangerouslySetInnerHTML={{ __html: THEME_BOOTSTRAP }}
          />
        ) : null}
      </head>
      <body>
        <a className="cn-skip-link" href="#main">
          Skip to main content
        </a>

        <main id="main" className={styles.main}>
          {children}
        </main>

        <ScrollRestoration />
        <Scripts />
      </body>
    </html>
  );
}

export default function App() {
  return <Outlet />;
}

export function ErrorBoundary() {
  const error = useRouteError();
  const rootData = useRouteLoaderData<typeof loader>('root');

  const status = errorStatus(error);

  // Mirrors `handleServerError`: a 4xx message is safe to show, a 5xx is not.
  const detail =
    status < 500 ? (asDetail(error) ?? 'Something went wrong.') : 'An unexpected error occurred.';
  const requestId = rootData?.requestId;

  return (
    <section className={errorStyles.error}>
      <p className={`${errorStyles.status} cn-numeric`}>{status}</p>
      <h1>{status === 404 ? 'Page not found' : 'Something went wrong'}</h1>
      <p className={errorStyles.detail}>{detail}</p>

      {requestId ? (
        <p className={errorStyles.requestId}>
          Reference <code className="cn-numeric">{requestId}</code>
        </p>
      ) : null}

      <a href="/dashboard">Back to dashboard</a>
    </section>
  );
}

function errorStatus(error: unknown): number {
  return isRouteErrorResponse(error) ? error.status : 500;
}

function asDetail(error: unknown): string | undefined {
  if (isRouteErrorResponse(error)) {
    if (typeof error.data === 'string' && error.data) return error.data;
    return error.statusText || undefined;
  }
  return error instanceof Error ? error.message : undefined;
}
