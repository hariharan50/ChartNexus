import { browser } from '$app/environment';

export type CallPutScheme = 'classic' | 'inverted';

const TOOLTIP_KEY = 'mc-pref-chart-tooltip';
const CALLPUT_KEY = 'mc-pref-callput';

/**
 * User display preferences that are not the colour theme: whether charts show a
 * hover tooltip, and which colour reads as Call vs Put.
 *
 * Persisted per-browser in localStorage today, matching how the theme store
 * works. The seam is deliberately small so a future account-level sync (a
 * `user_preferences` row) can back it without the consuming components changing.
 */
class PreferencesStore {
  #showChartTooltip = $state(true);
  #callPut = $state<CallPutScheme>('classic');

  get showChartTooltip(): boolean {
    return this.#showChartTooltip;
  }

  get callPutScheme(): CallPutScheme {
    return this.#callPut;
  }

  init(): void {
    if (!browser) return;
    const tooltip = localStorage.getItem(TOOLTIP_KEY);
    this.#showChartTooltip = tooltip === null ? true : tooltip === '1';
    const scheme = localStorage.getItem(CALLPUT_KEY);
    this.#callPut = scheme === 'inverted' ? 'inverted' : 'classic';
    this.#applyCallPut();
  }

  setShowChartTooltip(value: boolean): void {
    this.#showChartTooltip = value;
    if (browser) localStorage.setItem(TOOLTIP_KEY, value ? '1' : '0');
  }

  setCallPutScheme(scheme: CallPutScheme): void {
    this.#callPut = scheme;
    if (browser) {
      localStorage.setItem(CALLPUT_KEY, scheme);
      this.#applyCallPut();
    }
  }

  // Exposed on the root element so any component (or CSS) can react to the
  // chosen scheme without importing this store.
  #applyCallPut(): void {
    if (browser) document.documentElement.setAttribute('data-callput', this.#callPut);
  }
}

export const preferences = new PreferencesStore();
