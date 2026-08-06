import { create } from 'zustand';

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

interface ThemeState {
  theme: Theme;
  /** Adopt the attribute the server rendered / the user last chose. */
  init: () => void;
  set: (theme: Theme) => void;
  /** Quick light/dark flip for the header button. */
  toggle: () => void;
}

/**
 * The active colour theme, mirrored onto <html data-theme>.
 *
 * Dark is the default for the terminal (it runs all day), but the whole app is
 * tokenised for every theme. This store is the single writer of the
 * `data-theme` attribute so any toggle stays in sync with what the CSS reads.
 *
 * SSR note: this module-scope store is a singleton per Node process, shared by
 * every concurrent request. That is safe only because nothing writes to it
 * during render — `init` runs from an effect, `set`/`toggle` from event
 * handlers. Never call a setter from a loader or a component body.
 */
export const useThemeStore = create<ThemeState>()((set, get) => ({
  // Matches <html data-theme="dark"> in root.tsx, so the first client render
  // agrees with the server and `init` can adopt localStorage afterwards.
  theme: 'dark',

  init: () => {
    if (typeof document === 'undefined') return;
    const stored = localStorage.getItem(STORAGE_KEY) ?? '';
    const attr = document.documentElement.getAttribute('data-theme') ?? '';
    const candidate = (stored || attr) as Theme;
    const theme = KNOWN.has(candidate) ? candidate : 'dark';
    set({ theme });
    apply(theme);
  },

  set: (next) => {
    const theme = KNOWN.has(next) ? next : 'dark';
    set({ theme });
    if (typeof document === 'undefined') return;
    localStorage.setItem(STORAGE_KEY, theme);
    apply(theme);
  },

  toggle: () => {
    get().set(selectIsDark(get()) ? 'light' : 'dark');
  }
}));

/**
 * `isDark` was a getter on the Svelte class. As a selector it stays derived —
 * storing it as a field would let it drift out of step with `theme`.
 */
export const selectIsDark = (state: Pick<ThemeState, 'theme'>): boolean =>
  THEME_OPTIONS.find((option) => option.id === state.theme)?.dark ?? true;

function apply(theme: Theme): void {
  document.documentElement.setAttribute('data-theme', theme);
}
