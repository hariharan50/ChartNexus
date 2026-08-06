import { redirect } from 'react-router';

/**
 * `src/routes/+page.ts`: the app has no marketing homepage — `/` is the
 * dashboard. 307 keeps the method, matching what SvelteKit's `redirect(307)`
 * sent.
 */
export function loader(): never {
  throw redirect('/dashboard', 307);
}
