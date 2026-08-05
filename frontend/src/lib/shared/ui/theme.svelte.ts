import { browser } from '$app/environment';

export type Theme = 'light' | 'dark' | 'warm' | 'terminal';

interface ThemeOption {
  id: Theme;
  label: string;
  hint: string;
  /** Whether this theme reads as a dark surface (drives the header icon). */
  dark: boolean;
}

/** The themes offered in Settings, in display order. */
export const THEME_OPTIONS: readonly ThemeOption[] = [
  { id: 'light', label: 'Classic Blue', hint: 'Light & crisp', dark: false },
  { id: 'warm', label: 'Warm Cream', hint: 'Easy on the eyes', dark: false },
  { id: 'dark', label: 'Dark Mode', hint: 'Low-light slate', dark: true },
  { id: 'terminal', label: 'Classic Dark', hint: 'Pure black + terracotta', dark: true }
];

const KNOWN = new Set<Theme>(THEME_OPTIONS.map((option) => option.id));
const STORAGE_KEY = 'mc-theme';

/**
 * The active colour theme, mirrored onto <html data-theme>.
 *
 * Dark is the default for the terminal (it runs all day), but the whole app is
 * tokenised for every theme. This store is the single writer of the
 * `data-theme` attribute so any toggle stays in sync with what the CSS reads.
 */
class ThemeStore {
  #theme = $state<Theme>('dark');

  get value(): Theme {
    return this.#theme;
  }

  /** True for the dark-surface themes, so the header shows the right icon. */
  get isDark(): boolean {
    return THEME_OPTIONS.find((option) => option.id === this.#theme)?.dark ?? true;
  }

  /** Adopt the attribute the server rendered / the user last chose. */
  init(): void {
    if (!browser) return;
    const stored = localStorage.getItem(STORAGE_KEY) ?? '';
    const attr = document.documentElement.getAttribute('data-theme') ?? '';
    const candidate = (stored || attr) as Theme;
    this.#theme = KNOWN.has(candidate) ? candidate : 'dark';
    this.#apply();
  }

  set(theme: Theme): void {
    this.#theme = KNOWN.has(theme) ? theme : 'dark';
    if (browser) {
      localStorage.setItem(STORAGE_KEY, this.#theme);
      this.#apply();
    }
  }

  /** Quick light/dark flip for the header button. */
  toggle(): void {
    this.set(this.isDark ? 'light' : 'dark');
  }

  #apply(): void {
    document.documentElement.setAttribute('data-theme', this.#theme);
  }
}

export const theme = new ThemeStore();
