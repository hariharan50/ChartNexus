import { useEffect } from 'react';
import { useNotificationPreferencesStore } from './notification-preferences-store';
import { usePreferencesStore } from './preferences-store';
import { useThemeStore } from './theme-store';

/**
 * Adopts the browser's stored preferences once, after hydration.
 *
 * This is the literal translation of the `$effect` in `(terminal)/+layout.svelte`
 * that called `theme.init()`, `preferences.init()` and
 * `notificationPreferences.init()`.
 *
 * Running it in an effect rather than during render is what keeps hydration
 * clean: the server renders the store defaults, the first client render renders
 * the same defaults, and only then does localStorage win. Reading storage
 * during render would make the two disagree.
 */
export function useHydratePreferences(): void {
  useEffect(() => {
    useThemeStore.getState().init();
    usePreferencesStore.getState().init();
    useNotificationPreferencesStore.getState().init();
  }, []);
}
