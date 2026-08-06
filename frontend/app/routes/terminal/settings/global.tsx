import { cx } from '$shared/ui/cx';
import { usePreferencesStore, type CallPutScheme } from '$shared/ui/preferences-store';
import { THEME_OPTIONS, useThemeStore, type Theme } from '$shared/ui/theme-store';
import s from './global.module.css';
import type { Route } from './+types/global';

export const meta: Route.MetaFunction = () => [
  { title: 'Global Settings · Settings · MarketCompass' }
];

// Preview swatches per theme (fixed — they show the target theme, not the
// active one, so they must not read live tokens).
const PREVIEW: Record<Theme, { bg: string; panel: string; accent: string; bar: string }> = {
  light: { bg: '#f7f8fa', panel: '#ffffff', accent: '#2f6fe4', bar: '#dfe3eb' },
  warm: { bg: '#f4ede1', panel: '#fffdf8', accent: '#c8551f', bar: '#e6dccb' },
  dark: { bg: '#131722', panel: '#1a1f2e', accent: '#4c8dff', bar: '#2b3145' },
  terminal: { bg: '#0c0c0e', panel: '#16161a', accent: '#e2542a', bar: '#2a2a30' }
};

const callPut: { id: CallPutScheme; label: string; call: string; put: string }[] = [
  { id: 'classic', label: 'Classic', call: 'bullish', put: 'bearish' },
  { id: 'inverted', label: 'Inverted', call: 'bearish', put: 'bullish' }
];

export default function SettingsGlobal() {
  const showChartTooltip = usePreferencesStore((state) => state.showChartTooltip);
  const callPutScheme = usePreferencesStore((state) => state.callPutScheme);
  const setShowChartTooltip = usePreferencesStore((state) => state.setShowChartTooltip);
  const setCallPutScheme = usePreferencesStore((state) => state.setCallPutScheme);

  const activeTheme = useThemeStore((state) => state.theme);
  const setTheme = useThemeStore((state) => state.set);

  return (
    <>
      <h1 className={s.heading}>Global Settings</h1>

      {/* Chart */}
      <section className={cx(s.group, s.first)}>
        <p className={s.groupTitle}>Chart</p>
        <div className={s.toggleRow}>
          <div className={s.toggleCopy}>
            <p className={s.label}>Show chart tooltip</p>
            <p className={s.hint}>Reveal price &amp; OI details on chart hover</p>
          </div>
          <button
            type="button"
            role="switch"
            aria-checked={showChartTooltip}
            aria-label="Show chart tooltip"
            className={cx(s.switch, showChartTooltip && s.on)}
            onClick={() => setShowChartTooltip(!showChartTooltip)}
          >
            <span className={s.knob} />
          </button>
        </div>
      </section>

      {/* Call / Put colour */}
      <section className={s.group}>
        <p className={s.groupTitle}>Call / Put Colour</p>
        <div className={cx(s.cards, s.two)}>
          {callPut.map((scheme) => (
            <button
              key={scheme.id}
              type="button"
              className={cx(s.choice, callPutScheme === scheme.id && s.active)}
              aria-pressed={callPutScheme === scheme.id}
              onClick={() => setCallPutScheme(scheme.id)}
            >
              <span className={s.choiceHead}>
                <span className={s.choiceLabel}>{scheme.label}</span>
                {callPutScheme === scheme.id ? <span className={s.tick}>✓</span> : null}
              </span>
              <span className={s.legend}>
                <span className={s.leg}>
                  <span className={cx(s.dot, s[scheme.call])} />
                  Call
                </span>
                <span className={s.leg}>
                  <span className={cx(s.dot, s[scheme.put])} />
                  Put
                </span>
              </span>
            </button>
          ))}
        </div>
      </section>

      {/* Appearance */}
      <section className={s.group}>
        <p className={s.groupTitle}>Appearance — Theme</p>
        <div className={cx(s.cards, s.four)}>
          {THEME_OPTIONS.map((option) => {
            const p = PREVIEW[option.id];
            return (
              <button
                key={option.id}
                type="button"
                className={cx(s.themeCard, activeTheme === option.id && s.active)}
                aria-pressed={activeTheme === option.id}
                onClick={() => setTheme(option.id)}
              >
                <span className={s.preview} style={{ background: p.bg }}>
                  {activeTheme === option.id ? <span className={s.activeBadge}>Active</span> : null}
                  <span className={s.previewPanel} style={{ background: p.panel }}>
                    <span className={cx(s.bar, s.accent)} style={{ background: p.accent }} />
                    <span className={s.bar} style={{ background: p.bar }} />
                    <span className={cx(s.bar, s.short)} style={{ background: p.bar }} />
                  </span>
                </span>
                <span className={s.themeLabel}>{option.label}</span>
                <span className={s.themeHint}>{option.hint}</span>
              </button>
            );
          })}
        </div>
      </section>
    </>
  );
}
