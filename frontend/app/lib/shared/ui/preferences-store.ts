import { create } from 'zustand';

export type CallPutScheme = 'classic' | 'inverted';

const TOOLTIP_KEY = 'cn-pref-chart-tooltip';
const CALLPUT_KEY = 'cn-pref-callput';

interface PreferencesState {
  showChartTooltip: boolean;
  callPutScheme: CallPutScheme;
  init: () => void;
  setShowChartTooltip: (value: boolean) => void;
  setCallPutScheme: (scheme: CallPutScheme) => void;
}

/**
 * User display preferences that are not the colour theme: whether charts show a
 * hover tooltip, and which colour reads as Call vs Put.
 *
 * Persisted per-browser in localStorage today, matching how the theme store
 * works. The seam is deliberately small so a future account-level sync (a
 * `user_preferences` row) can back it without the consuming components changing.
 *
 * See the SSR-singleton note in theme-store.ts: never set from render.
 */
export const usePreferencesStore = create<PreferencesState>()((set) => ({
  showChartTooltip: true,
  callPutScheme: 'classic',

  init: () => {
    if (typeof document === 'undefined') return;
    const tooltip = localStorage.getItem(TOOLTIP_KEY);
    const scheme = localStorage.getItem(CALLPUT_KEY);
    const callPutScheme: CallPutScheme = scheme === 'inverted' ? 'inverted' : 'classic';

    set({
      showChartTooltip: tooltip === null ? true : tooltip === '1',
      callPutScheme
    });
    applyCallPut(callPutScheme);
  },

  setShowChartTooltip: (value) => {
    set({ showChartTooltip: value });
    if (typeof document === 'undefined') return;
    localStorage.setItem(TOOLTIP_KEY, value ? '1' : '0');
  },

  setCallPutScheme: (scheme) => {
    set({ callPutScheme: scheme });
    if (typeof document === 'undefined') return;
    localStorage.setItem(CALLPUT_KEY, scheme);
    applyCallPut(scheme);
  }
}));

// Exposed on the root element so any component (or CSS) can react to the
// chosen scheme without importing this store.
function applyCallPut(scheme: CallPutScheme): void {
  document.documentElement.setAttribute('data-callput', scheme);
}
