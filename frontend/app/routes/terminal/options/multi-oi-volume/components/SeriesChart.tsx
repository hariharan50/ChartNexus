import { useMemo, useState, type ReactNode } from 'react';
import EChart from '$shared/charts/EChart';
import { buildMultiSeriesOption, type SeriesLine } from '$shared/charts/options/multi-series';
import { useChartTheme } from '$shared/charts/theme/use-chart-theme';
import { cx } from '$shared/ui/cx';
import s from './SeriesChart.module.css';

/**
 * One titled panel: an eye-toggle legend over a multi-series line chart.
 *
 * Visibility is held here rather than in ECharts' own legend. The reference
 * design puts an eye on every entry, which the built-in legend cannot draw, and
 * keeping the toggles in React means the option is rebuilt with only the
 * visible series — so a hidden line costs nothing to render rather than being
 * drawn and then masked.
 */
interface Props {
  title: string;
  icon: ReactNode;
  lines: SeriesLine[];
  times: string[];
  futures: (number | null)[];
  formatValue: (value: number) => string;
  formatPrice: (value: number) => string;
  /** Charts sharing a group id share one crosshair. */
  group: string;
  empty?: string;
}

export default function SeriesChart({
  title,
  icon,
  lines,
  times,
  futures,
  formatValue,
  formatPrice,
  group,
  empty
}: Props) {
  const [hidden, setHidden] = useState<Set<string>>(() => new Set());
  const [futuresOn, setFuturesOn] = useState(true);
  const theme = useChartTheme();

  function toggle(id: string) {
    setHidden((current) => {
      const next = new Set(current);
      if (!next.delete(id)) next.add(id);
      return next;
    });
  }

  const visible = useMemo(() => lines.filter((line) => !hidden.has(line.id)), [lines, hidden]);

  const option = useMemo(
    () =>
      buildMultiSeriesOption(
        { times, futures, lines: visible, formatValue, formatPrice, showFutures: futuresOn },
        theme
      ),
    [times, futures, visible, formatValue, formatPrice, futuresOn, theme]
  );

  return (
    <section className={s.panel}>
      <h2 className={s.title}>
        <span className={s.ico} aria-hidden="true">
          {icon}
        </span>{' '}
        {title}
      </h2>

      <div className={s.legend}>
        <button
          type="button"
          className={cx(s.entry, !futuresOn && s.off)}
          onClick={() => setFuturesOn((on) => !on)}
          aria-pressed={futuresOn}
        >
          <Eye on={futuresOn} />
          <span className={s.dash} aria-hidden="true" />
          Future
        </button>
        {lines.map((line) => {
          const on = !hidden.has(line.id);
          return (
            <button
              key={line.id}
              type="button"
              className={cx(s.entry, !on && s.off)}
              onClick={() => toggle(line.id)}
              aria-pressed={on}
              style={{ color: on ? line.color : undefined }}
            >
              <Eye on={on} />
              {line.label}
            </button>
          );
        })}
      </div>

      {times.length === 0 ? (
        <p className={s.empty}>{empty ?? 'No intraday history recorded yet.'}</p>
      ) : (
        <EChart option={option} className={s.chart} group={group} />
      )}
    </section>
  );
}

/** Open eye when shown, struck through when hidden. */
function Eye({ on }: { on: boolean }) {
  return (
    <svg viewBox="0 0 16 16" className={s.eye} aria-hidden="true">
      <path
        d="M1 8s2.5-4.5 7-4.5S15 8 15 8s-2.5 4.5-7 4.5S1 8 1 8Z"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.3"
      />
      <circle cx="8" cy="8" r="1.9" fill="currentColor" />
      {!on ? <path d="M2 14 14 2" stroke="currentColor" strokeWidth="1.3" /> : null}
    </svg>
  );
}
