import type { MeasurementStats } from '$shared/charts/tv/drawings/useDrawingController';
import { cx } from '$shared/ui/cx';
import { fmtPrice } from '../analyse-data';
import s from './MeasureReadout.module.css';

/**
 * The ruler tool's readout: Δprice, Δ% and bar count between its two clicks.
 *
 * A sibling of `ChartLegend` — same absolutely-positioned-over-the-canvas
 * approach — but pinned to the opposite corner so the two never collide, and
 * transient rather than always-on: it only exists while the measure tool has
 * an anchor placed.
 */
interface Props {
  stats: MeasurementStats;
}

export default function MeasureReadout({ stats }: Props) {
  const up = stats.deltaPrice >= 0;
  return (
    <div className={s.readout}>
      <span className={cx(s.delta, up ? s.up : s.down)}>
        {up ? '+' : ''}
        {fmtPrice(stats.deltaPrice)} ({up ? '+' : ''}
        {stats.deltaPercent.toFixed(2)}%)
      </span>
      <span className={s.bars}>{stats.bars} bars</span>
    </div>
  );
}
