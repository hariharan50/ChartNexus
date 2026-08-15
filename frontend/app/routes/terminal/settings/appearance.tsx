import { cx } from '$shared/ui/cx';
import { THEME_OPTIONS, useThemeStore, type Theme } from '$shared/ui/theme-store';
import s from './appearance.module.css';
import type { Route } from './+types/appearance';

export const meta: Route.MetaFunction = () => [{ title: 'Layout · Settings · MarketCompass' }];

/**
 * A mini snapshot of each theme, built from that theme's *fixed* palette rather
 * than live tokens — the cards must show the target theme while the app around
 * them stays on the active one. Values mirror the corresponding block in
 * app.css; keep them in step when a palette changes.
 */
interface Swatch {
  bg: string;
  nav: string;
  panel: string;
  border: string;
  accent: string;
  text: string;
  up: string;
  down: string;
}

const SWATCH: Record<Theme, Swatch> = {
  light: {
    bg: '#f7f8fa',
    nav: '#ffffff',
    panel: '#ffffff',
    border: '#dfe3eb',
    accent: '#2f6fe4',
    text: '#131722',
    up: '#0e9f63',
    down: '#d92b45'
  },
  warm: {
    bg: '#f4ede1',
    nav: '#fffdf8',
    panel: '#fffdf8',
    border: '#e6dccb',
    accent: '#c8551f',
    text: '#2b2620',
    up: '#2f855a',
    down: '#c0392b'
  },
  dark: {
    bg: '#0b0e14',
    nav: '#131722',
    panel: '#1a1f2e',
    border: '#262b3a',
    accent: '#4c8dff',
    text: '#e6e9f0',
    up: '#17b877',
    down: '#f2495c'
  },
  midnight: {
    bg: '#0a0c12',
    nav: '#12151e',
    panel: '#181c28',
    border: '#1f2534',
    accent: '#f0623a',
    text: '#eceff5',
    up: '#17b877',
    down: '#f2495c'
  },
  terminal: {
    bg: '#000000',
    nav: '#0c0c0e',
    panel: '#16161a',
    border: '#24242a',
    accent: '#e2542a',
    text: '#ededf0',
    up: '#17b877',
    down: '#f2495c'
  }
};

const GROUPS: { title: string; dark: boolean }[] = [
  { title: 'Light', dark: false },
  { title: 'Dark', dark: true }
];

export default function SettingsAppearance() {
  const activeTheme = useThemeStore((state) => state.theme);
  const setTheme = useThemeStore((state) => state.set);

  return (
    <>
      <h1 className={s.heading}>Layout</h1>
      <p className={s.intro}>
        Choose how MarketCompass looks. Light is the crisp daytime layout; the dark layouts are
        tuned for long, low-light trading sessions. Your choice is saved on this device and applies
        everywhere in the app.
      </p>

      {GROUPS.map((group) => {
        const themes = THEME_OPTIONS.filter((option) => option.dark === group.dark);
        return (
          <section key={group.title} className={s.group}>
            <p className={s.groupTitle}>{group.title}</p>
            <div className={s.grid}>
              {themes.map((option) => {
                const p = SWATCH[option.id];
                const active = activeTheme === option.id;
                return (
                  <button
                    key={option.id}
                    type="button"
                    className={cx(s.card, active && s.active)}
                    aria-pressed={active}
                    onClick={() => setTheme(option.id)}
                  >
                    {/* A miniature terminal rendered from the theme's own palette. */}
                    <span className={s.preview} style={{ background: p.bg }} aria-hidden="true">
                      <span
                        className={s.previewNav}
                        style={{ background: p.nav, borderColor: p.border }}
                      >
                        <span className={s.previewDot} style={{ background: p.accent }} />
                        <span className={s.previewNavBar} style={{ background: p.border }} />
                        <span
                          className={cx(s.previewNavBar, s.short)}
                          style={{ background: p.border }}
                        />
                      </span>
                      <span className={s.previewBody}>
                        <span
                          className={s.previewCard}
                          style={{ background: p.panel, borderColor: p.border }}
                        >
                          <span className={s.previewBar} style={{ background: p.border }} />
                          <span
                            className={cx(s.previewBar, s.value)}
                            style={{ background: p.up }}
                          />
                        </span>
                        <span
                          className={s.previewCard}
                          style={{ background: p.panel, borderColor: p.border }}
                        >
                          <span className={s.previewBar} style={{ background: p.border }} />
                          <span
                            className={cx(s.previewBar, s.value)}
                            style={{ background: p.down }}
                          />
                        </span>
                      </span>
                      {active ? <span className={s.activeBadge}>Active</span> : null}
                    </span>

                    <span className={s.meta}>
                      <span className={s.label}>{option.label}</span>
                      {active ? <span className={s.tick}>✓</span> : null}
                    </span>
                    <span className={s.hint}>{option.hint}</span>
                  </button>
                );
              })}
            </div>
          </section>
        );
      })}
    </>
  );
}
