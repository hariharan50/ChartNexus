import { browser } from '$app/environment';

export type Theme = 'dark' | 'light';

const STORAGE_KEY = 'mc-theme';

/**
 * The active colour theme, mirrored onto <html data-theme>.
 *
 * Dark is the default for the terminal (it runs all day), but the whole app is
 * tokenised for both. This store is the single writer of the `data-theme`
 * attribute so any toggle stays in sync with what the CSS actually reads.
 */
class ThemeStore {
  #theme = $state<Theme>('dark');

  get value(): Theme {
    return this.#theme;
  }

  /** Adopt the attribute the server rendered / the user last chose. */
  init(): void {
    if (!browser) return;
    const stored = localStorage.getItem(STORAGE_KEY);
    const attr = document.documentElement.getAttribute('data-theme');
    this.#theme = (stored ?? attr) === 'light' ? 'light' : 'dark';
    this.#apply();
  }

  set(theme: Theme): void {
    this.#theme = theme;
    if (browser) {
      localStorage.setItem(STORAGE_KEY, theme);
      this.#apply();
    }
  }

  toggle(): void {
    this.set(this.#theme === 'dark' ? 'light' : 'dark');
  }

  #apply(): void {
    document.documentElement.setAttribute('data-theme', this.#theme);
  }
}

export const theme = new ThemeStore();
