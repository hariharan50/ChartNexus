import { useQueryClient } from '@tanstack/react-query';
import { useCallback } from 'react';
import { useNavigate, useRevalidator, useRouteLoaderData } from 'react-router';
import * as api from './api';
import type { User } from './types';

/**
 * The signed-in user.
 *
 * There is no store here on purpose. Svelte's `SessionStore` existed to carry
 * the profile from the layout `load` down to the components; React Router hands
 * loader data to every descendant directly, and a second copy in a client store
 * could only ever go stale. Tokens are httpOnly cookies the browser cannot
 * read, so there was never anything token-shaped to keep in memory either.
 */

const TERMINAL_LAYOUT_ROUTE_ID = 'routes/terminal/layout';

/** The profile loaded by the terminal route guard. `null` outside that group. */
export function useUser(): User | null {
  const data = useRouteLoaderData(TERMINAL_LAYOUT_ROUTE_ID) as { user: User } | undefined;
  return data?.user ?? null;
}

export function useIsAuthenticated(): boolean {
  return useUser() !== null;
}

/**
 * Re-runs the guard loader, which is what `session.refreshProfile()` did.
 * Also the replacement for SvelteKit's `invalidateAll()`.
 */
export function useRefreshProfile(): () => void {
  const revalidator = useRevalidator();
  return useCallback(() => {
    void revalidator.revalidate();
  }, [revalidator]);
}

export function useSignOut(): (redirectTo?: string) => Promise<void> {
  const navigate = useNavigate();
  const revalidator = useRevalidator();
  const queryClient = useQueryClient();

  return useCallback(
    async (redirectTo = '/login') => {
      try {
        await api.logout();
      } finally {
        // Leave even if the call failed — the user asked to, and the cookies
        // are gone or unusable either way. Clearing the query cache matters
        // here: it holds the previous user's market data and profile reads.
        queryClient.clear();
        await navigate(redirectTo);
        void revalidator.revalidate();
      }
    },
    [navigate, queryClient, revalidator]
  );
}
