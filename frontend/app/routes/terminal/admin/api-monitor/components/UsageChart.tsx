import { useMemo } from 'react';
import { formatCount, formatMs } from '$contexts/api-monitor/api';
import type { SeriesPoint } from '$contexts/api-monitor/types';
import s from './UsageChart.module.css';

/**
 * Calls per step as bars, p95 latency as a line over them.
 *
 * Plain SVG on purpose: two series over at most ~170 points needs no charting
 * library, and this keeps the monitor free of the chart stack the trading
 * pages depend on. Scales to its container; colours come from CSS tokens so it
 * follows the theme.
 */
const W = 600;
const H = 160;
const PAD_TOP = 10;
const PAD_BOTTOM = 4;

interface Props {
  series: SeriesPoint[];
  stepSeconds: number;
  height?: number;
  compact?: boolean;
}

export default function UsageChart({ series, stepSeconds, height = H, compact = false }: Props) {
  const shape = useMemo(() => {
    const maxCalls = Math.max(1, ...series.map((point) => point.calls));
    const latencies = series.map((point) => point.p95_ms ?? 0);
    const maxLatency = Math.max(1, ...latencies);
    const slot = W / Math.max(1, series.length);
    const usable = H - PAD_TOP - PAD_BOTTOM;
    const bars = series.map((point, index) => {
      const barHeight = (point.calls / maxCalls) * usable;
      const errorHeight = point.calls ? (point.errors / point.calls) * barHeight : 0;
      return {
        x: index * slot + slot * 0.15,
        width: Math.max(1, slot * 0.7),
        y: H - PAD_BOTTOM - barHeight,
        height: barHeight,
        errorHeight
      };
    });
    const line = series
      .map((point, index) =>
        point.p95_ms === null
          ? null
          : `${(index * slot + slot / 2).toFixed(1)},${(
              H -
              PAD_BOTTOM -
              (point.p95_ms / maxLatency) * usable
            ).toFixed(1)}`
      )
      .filter((value): value is string => value !== null);
    return { bars, line, maxCalls, maxLatency };
  }, [series]);

  const total = series.reduce((sum, point) => sum + point.calls, 0);
  const perStep = stepSeconds >= 3600 ? 'hour' : `${Math.round(stepSeconds / 60)} min`;

  return (
    <figure className={s.figure}>
      {compact ? null : (
        <figcaption className={s.legend}>
          <span>
            <i className={s.keyCalls} aria-hidden="true" /> Calls per {perStep} (peak{' '}
            {formatCount(shape.maxCalls)})
          </span>
          <span>
            <i className={s.keyErrors} aria-hidden="true" /> Errors
          </span>
          <span>
            <i className={s.keyLatency} aria-hidden="true" /> p95 latency (peak{' '}
            {formatMs(shape.maxLatency)})
          </span>
        </figcaption>
      )}
      <svg
        className={s.svg}
        viewBox={`0 0 ${W} ${H}`}
        preserveAspectRatio="none"
        style={{ height }}
        role="img"
        aria-label={`${formatCount(total)} calls over the selected range`}
      >
        <line className={s.axis} x1={0} x2={W} y1={H - PAD_BOTTOM} y2={H - PAD_BOTTOM} />
        {shape.bars.map((bar, index) => (
          <g key={index}>
            <rect className={s.bar} x={bar.x} width={bar.width} y={bar.y} height={bar.height} />
            {bar.errorHeight > 0 ? (
              <rect
                className={s.errorBar}
                x={bar.x}
                width={bar.width}
                y={H - PAD_BOTTOM - bar.errorHeight}
                height={bar.errorHeight}
              />
            ) : null}
          </g>
        ))}
        {shape.line.length > 1 ? (
          <polyline
            className={s.latency}
            points={shape.line.join(' ')}
            vectorEffect="non-scaling-stroke"
          />
        ) : null}
      </svg>
      {total === 0 ? <p className={s.empty}>No calls recorded in this range yet.</p> : null}
    </figure>
  );
}
