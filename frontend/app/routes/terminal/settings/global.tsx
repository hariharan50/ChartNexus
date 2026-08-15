import { cx } from '$shared/ui/cx';
import { usePreferencesStore, type CallPutScheme } from '$shared/ui/preferences-store';
import s from './global.module.css';
import type { Route } from './+types/global';

export const meta: Route.MetaFunction = () => [
  { title: 'Global Settings · Settings · MarketCompass' }
];

const callPut: { id: CallPutScheme; label: string; call: string; put: string }[] = [
  { id: 'classic', label: 'Classic', call: 'bullish', put: 'bearish' },
  { id: 'inverted', label: 'Inverted', call: 'bearish', put: 'bullish' }
];

export default function SettingsGlobal() {
  const showChartTooltip = usePreferencesStore((state) => state.showChartTooltip);
  const callPutScheme = usePreferencesStore((state) => state.callPutScheme);
  const setShowChartTooltip = usePreferencesStore((state) => state.setShowChartTooltip);
  const setCallPutScheme = usePreferencesStore((state) => state.setCallPutScheme);

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
    </>
  );
}
