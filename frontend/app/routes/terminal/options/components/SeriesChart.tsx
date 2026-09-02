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
  /** One line under the title saying what the chart is for. */
  subtitle: string;
  icon: ReactNode;
  /** What the right axis measures. */
  valueAxisName: string;
  /** A horizontal marker on the value axis, e.g. PCR = 1. */
  referenceLine?: { value: number; label: string } | undefined;
  lines: SeriesLine[];
  /**
   * ISO timestamps, one per point — not display strings.
   *
   * The axis is measured in elapsed trading time and needs to know when each
   * point actually was; handing it pre-formatted clock text is what made every
   * gap draw the same width regardless of how long it really was.
   */
  timestamps: string[];
  futures: (number | null)[];
  formatValue: (value: number) => string;
  formatPrice: (value: number) => string;
  /** Charts sharing a group id share one crosshair. */
  group: string;
  /**
   * Draw only up to this index — the replay head.
   *
   * Truncating here rather than in the caller keeps the head out of the route's
   * per-chart `useMemo` dependency lists, so a sweep re-derives one option
   * object per frame instead of every series array on the page.
   */
  head?: number | undefined;
  empty?: string;
  /** Give the plot the width back on a narrow panel — see `buildMultiSeriesOption`. */
  compact?: boolean | undefined;
  /**
   * Let the reader work the time axis: wheel to zoom, drag inside the plot to
   * pan, drag the clock strip to stretch or squeeze the window. Adds a Reset
   * zoom control beside the legend.
   *
   * Opt-in: a chart that takes the wheel stops the page scrolling over it, which
   * is only worth it where people read into the chart rather than glance at it.
   */
  zoomable?: boolean | undefined;
  /**
   * Reset-zoom wiring, owned by the page rather than the panel.
   *
   * Panels sharing a `group` share a window, so a reset has to land on all of
   * them: a rebuild only re-applies the option's own window to the chart being
   * rebuilt, and the group syncs actions, not `setOption`. The page bumps
   * `zoomEpoch` and every panel rebuilds together.
   */
  zoomEpoch?: number | undefined;
  onResetZoom?: (() => void) | undefined;
}

export default function SeriesChart({
  title,
  subtitle,
  icon,
  valueAxisName,
  referenceLine,
  lines,
  timestamps,
  futures,
  formatValue,
  formatPrice,
  group,
  head,
  empty,
  compact,
  zoomable,
  zoomEpoch = 0,
  onResetZoom
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

  const shown = useMemo(() => (head === undefined ? lines : truncate(lines, head)), [lines, head]);
  const shownTimes = useMemo(
    () => (head === undefined ? timestamps : timestamps.slice(0, head + 1)),
    [timestamps, head]
  );
  const shownFutures = useMemo(
    () => (head === undefined ? futures : futures.slice(0, head + 1)),
    [futures, head]
  );

  const visible = useMemo(() => shown.filter((line) => !hidden.has(line.id)), [shown, hidden]);

  const option = useMemo(
    () =>
      buildMultiSeriesOption(
        {
          timestamps: shownTimes,
          futures: shownFutures,
          lines: visible,
          formatValue,
          formatPrice,
          valueAxisName,
          referenceLine,
          showFutures: futuresOn,
          compact,
          zoomable
        },
        theme
      ),
    [
      shownTimes,
      shownFutures,
      visible,
      formatValue,
      formatPrice,
      valueAxisName,
      referenceLine,
      futuresOn,
      compact,
      zoomable,
      theme
    ]
  );

  return (
    <section className={s.panel}>
      <h2 className={s.title}>
        <span className={s.ico} aria-hidden="true">
          {icon}
        </span>{' '}
        {title}
      </h2>
      <p className={s.subtitle}>{subtitle}</p>

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
        {zoomable && onResetZoom ? (
          <button
            type="button"
            className={s.zoomReset}
            onClick={onResetZoom}
            title="Back to the whole session — every panel"
          >
            ⤢ Reset zoom
          </button>
        ) : null}
      </div>

      {shownTimes.length === 0 ? (
        <p className={s.empty}>{empty ?? 'No intraday history recorded yet.'}</p>
      ) : (
        <EChart
          option={option}
          className={s.chart}
          group={group}
          resetKey={zoomable ? `zoom-${zoomEpoch}` : undefined}
        />
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

/** The visible slice of every line, up to and including `head`. */
function truncate(lines: SeriesLine[], head: number): SeriesLine[] {
  return lines.map((line) => ({ ...line, values: line.values.slice(0, head + 1) }));
}
