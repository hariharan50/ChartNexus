import { redirect } from '@sveltejs/kit';
import { currentUser } from '$contexts/identity/api';
import { isApiError } from '$shared/api/errors';
import type { LayoutLoad } from './$types';

/**
 * Gate for every terminal route.
 *
 * This is a convenience redirect, not the security boundary — the API
 * authorises every request on its own. Its job is to send a signed-out visitor
 * to the sign-in page instead of showing them an empty shell full of 401s.
 */
export const load: LayoutLoad = async ({ fetch, url }) => {
  try {
    // SvelteKit's fetch forwards cookies during SSR; the browser sends them itself.
    const user = await currentUser(fetch);
    return { user };
  } catch (error) {
    if (isApiError(error) && (error.status === 401 || error.status === 403)) {
      const next = url.pathname + url.search;
      redirect(303, `/login?next=${encodeURIComponent(next)}`);
    }
    throw error;
  }
};
