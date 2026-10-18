import { describe, expect, it } from 'vitest';
import { loader } from '../../app/routes/terminal/options/retired.tsx';

/**
 * Retired Options Lab modules.
 *
 * `Timeseries` and `PE-CE Difference` were removed from the Lab. Deleting the
 * route files was not sufficient on its own: an address that matches nothing
 * throws the reader onto the *root* error page ("No route matches URL …"),
 * outside the terminal shell, and open tabs and bookmarks still point at the
 * old URLs. `routes.ts` therefore keeps both paths registered against this
 * module, whose only job is to hand the reader back to the Lab.
 *
 * What this pins is the redirect itself, which an HTTP check cannot reach: the
 * terminal layout's auth guard runs first and answers unauthenticated requests
 * with a 303 to `/login`, masking the status below.
 */
describe('retired options module', () => {
  it('redirects to the Options Lab index', () => {
    // The loader signals by throwing, the way `redirect()` is meant to be used
    // in a loader — a returned value here would render instead of navigating.
    expect.assertions(2);
    try {
      loader();
    } catch (thrown) {
      const response = thrown as Response;
      expect(response.status).toBe(301);
      expect(response.headers.get('Location')).toBe('/options');
    }
  });
});
