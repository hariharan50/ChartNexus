import { cx } from '$shared/ui/cx';
import { fmtStrike, type GexLevel } from '../gex-data';
import s from './GexLevels.module.css';

/**
 * The four derived levels, as text.
 *
 * Not a duplicate of the marker chips on the chart. The chart is a canvas, so
 * with Show Walls and Show Flip both off it gives no readable confirmation of
 * what those toggles did — and the levels are the page's actual output, the
 * numbers someone writes down. They stay legible here whatever the toggles say,
 * and carry the distance from spot, which a chip pinned to a gridline cannot.
 *
 * A level the book does not have renders as an em dash with its reason. Drawing
 * `0` there, or hiding the cell, would both read as "no wall today" rather than
 * "this chain is one-sided".
 */
interface Props {
  levels: GexLevel[];
  /** Which levels are currently drawn on the chart, by id. */
  shown: ReadonlySet<string>;
  colors: Record<string, string>;
}

export default function GexLevels({ levels, shown, colors }: Props) {
  return (
    <ul className={s.grid}>
      {levels.map((level) => (
        <li key={level.id} className={s.cell} title={level.hint}>
          <span className={s.head}>
            <i
              className={cx(s.swatch, !shown.has(level.id) && s.muted)}
              style={{ background: colors[level.id] }}
              aria-hidden="true"
            />
            <span className={s.label}>{level.label}</span>
          </span>

          {level.strike === null ? (
            <>
              <span className={cx(s.value, s.absent)}>—</span>
              <span className={s.gap}>not in this book</span>
            </>
          ) : (
            <>
              <span className={s.value}>{fmtStrike(level.strike)}</span>
              <span className={cx(s.gap, (level.gap ?? 0) >= 0 ? s.up : s.down)}>
                {(level.gap ?? 0) >= 0 ? '+' : ''}
                {Math.round(level.gap ?? 0)} from spot
              </span>
            </>
          )}
        </li>
      ))}
    </ul>
  );
}
