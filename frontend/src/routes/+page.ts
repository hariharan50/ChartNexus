import { redirect } from '@sveltejs/kit';

/** The root path has no page of its own — the terminal starts at the dashboard. */
export function load(): never {
  redirect(307, '/dashboard');
}
