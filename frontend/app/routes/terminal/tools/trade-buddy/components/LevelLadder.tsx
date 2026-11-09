import { cx } from '$shared/ui/cx';
import {
  ladderScaleX,
  nearestLevel,
  stateLook,
  type ResolvedBands,
  type WatcherState
} from '../trade-buddy-data';
import s from './LevelLadder.module.css';

/**
 * Where price sits among the marked levels, on one shared axis.
 *
 * The table beside this says *what* each level is doing; the map says *how far
 * away* it is, which a column of numbers cannot. That distance is the whole
 * reason to look: "R1 touched" and "R1 forty points off" are different
 * decisions, and only one of them is in the state column.
 *
 * Horizontal now, not vertical. A tall column fought the table it sits above
 * for the same vertical space and pushed the levels themselves below the fold;
 * price on a left-to-right axis costs 80px and reads the way a chart's price
 * axis does when you turn your head. Low prices on the left, so "price is
 * nearly at R1" means the cursor is near the right-hand ticks.
 *
 * Deliberately spare: one quantitative axis, six ticks, a cursor and one
 * shaded band. State only *weights* a tick — the word and the glyph are in the
 * table — so the picture stays readable in greyscale and under colour-vision
 * deficiency. It is `aria-hidden` in full: every number in it is in the table
 * below, and a screen reader does not need the same six prices twice.
 */
interface Props {
  levels: readonly WatcherState[];
  price: number | null;
  bands: ResolvedBands | undefined;
}

export default function LevelLadder({ levels, price, bands }: Props) {
  const scale = ladderScaleX(levels, price);

  // One level and no price is a line with nothing to be relative to. The table
  // already carries every number, so omitting the picture loses nothing.
  if (!scale) return null;

  const nearest = nearestLevel(levels, price);
  const approach = bands?.approach ?? null;

  return (
    <figure className={s.figure}>
      <div className={s.frame} aria-hidden="true">
        {/* The approach band around the level price is closest to. Shown for
            one level rather than all six: six overlapping bands on a 500px
            axis is a wash, and only the nearest one is about to matter. */}
        {nearest && approach !== null && (
          <span
            className={cx(
              s.zone,
              nearest.level.role === 'support' ? s.zoneSupport : s.zoneResistance
            )}
            style={{
              left: `${scale(nearest.level.level_price - approach) * 100}%`,
              right: `${(1 - scale(nearest.level.level_price + approach)) * 100}%`
            }}
          />
        )}

        <span className={s.axis} />

        {levels.map((level) => {
          const look = stateLook(level.state);
          return (
            <span
              key={level.label}
              className={cx(
                s.level,
                level.role === 'support' ? s.support : s.resistance,
                s[`tone_${look.tone}`]
              )}
              style={{ left: `${scale(level.level_price) * 100}%` }}
            >
              <span className={s.tick} />
              <span className={s.label}>{level.label}</span>
              <span className={s.levelPrice}>
                {level.level_price.toLocaleString('en-IN', { maximumFractionDigits: 0 })}
              </span>
            </span>
          );
        })}

        {price !== null && (
          <span className={s.cursor} style={{ left: `${scale(price) * 100}%` }}>
            <span className={s.cursorChip}>
              {price.toLocaleString('en-IN', { maximumFractionDigits: 0 })}
            </span>
            <span className={s.cursorLine} />
          </span>
        )}
      </div>

      <figcaption className={s.caption}>Marked levels and last price, to scale.</figcaption>
    </figure>
  );
}
