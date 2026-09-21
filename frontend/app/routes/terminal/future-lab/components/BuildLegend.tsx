import type { FuturesRow } from '$contexts/futures-analytics/types';
import { cx } from '$shared/ui/cx';
import { countByState } from '../stocks-data';
import s from './BuildLegend.module.css';

/**
 * How the whole board is positioned, in one line.
 *
 * The counts are the board's summary statistic: 117 contracts short-covering
 * against 21 building shorts says more about the session than any single row.
 * Zero-count states stay visible so the line does not reflow as the market
 * moves — a row of numbers that jumps around is hard to read at a glance.
 */
interface Props {
  rows: FuturesRow[];
  /** The state currently filtered to, if any — highlighted here as well as in
   *  the toolbar, since this is where the eye already is. */
  active?: string | null;
  onPick?: (state: string | null) => void;
}

export default function BuildLegend({ rows, active = null, onPick }: Props) {
  const counts = countByState(rows);

  return (
    <div className={s.legend} role="group" aria-label="Build-up breakdown">
      {counts.map(({ meta, count }) => {
        const selected = active === meta.id;
        return (
          <button
            key={meta.id}
            type="button"
            className={cx(s.item, selected && s.selected)}
            aria-pressed={selected}
            // Clicking a legend entry is the fastest way to isolate a state,
            // and clicking it again clears the filter.
            onClick={() => onPick?.(selected ? null : meta.id)}
          >
            <span className={cx(s.swatch, s[meta.tone])} aria-hidden="true" />
            <span className={s.label}>{meta.label}</span>
            <span className={s.count}>{count}</span>
          </button>
        );
      })}
    </div>
  );
}
