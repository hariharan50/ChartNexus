import { useCallback, useEffect, useState } from 'react';

/**
 * Light/dark theme, scoped to the marketing landing page alone.
 *
 * Deliberately independent of the app-wide theme store (`mc-theme` /
 * `<html data-theme>`): the landing carries a bespoke dark design and must not
 * flip the terminal's theme, so it uses its own attribute and storage key.
 *
 * The attribute lives on `<html>` (not the `.landing` div) so the pre-paint
 * bootstrap in `root.tsx` can set it before first paint — a returning
 * light-mode visitor sees no dark flash. This hook is the only client writer of
 * the attribute, mirroring how the app's theme store owns `data-theme`.
 */
const STORAGE_KEY = 'mc-landing-theme';
const ATTR = 'data-lp-theme';

type LandingTheme = 'light' | 'dark';

function readInitial(): LandingTheme {
  if (typeof document === 'undefined') return 'dark';
  if (document.documentElement.getAttribute(ATTR) === 'light') return 'light';
  try {
    if (localStorage.getItem(STORAGE_KEY) === 'light') return 'light';
  } catch {
    // localStorage unavailable (private mode / blocked) — fall back to dark.
  }
  return 'dark';
}

function apply(theme: LandingTheme) {
  const root = document.documentElement;
  if (theme === 'light') root.setAttribute(ATTR, 'light');
  else root.removeAttribute(ATTR);
}

export function useLandingTheme() {
  // Server and first client render both resolve to 'dark' (the document ships
  // without the attribute), so hydration matches; the effect then corrects a
  // light-mode visitor a frame later.
  const [theme, setTheme] = useState<LandingTheme>('dark');

  useEffect(() => {
    setTheme(readInitial());
  }, []);

  const toggle = useCallback(() => {
    setTheme((prev) => {
      const next: LandingTheme = prev === 'dark' ? 'light' : 'dark';
      try {
        localStorage.setItem(STORAGE_KEY, next);
      } catch {
        // Persisting is best-effort; the in-page toggle still works this session.
      }
      apply(next);
      return next;
    });
  }, []);

  return { isDark: theme === 'dark', toggle };
}
