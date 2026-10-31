import { cx } from '$shared/ui/cx';
import { formatPrice, ladderScale, stateLook, type WatcherState } from '../trade-buddy-data';
import s from './LevelLadder.module.css';

/**
 * Where price sits among the marked levels, on one shared vertical scale.
 *
 * The table beside this says *what* each level is doing; the ladder says *how
 * far away* it is, which a column of numbers cannot. That distance is the whole
 * reason to look: "R1 touched" and "R1 forty points off" are different
 * decisions, and only one of them is in the state column.
 *
 * Positional, not a chart in the usual sense — one quantitative axis, six marks
 * and a cursor. Deliberately spare: a grid, gradients or a second axis would
 * add ink without adding an answer. State is carried by a text label and a
 * glyph in the table; here it only *weights* a line, so the picture stays
 * readable in greyscale and under colour-vision deficiency.
 */
interface Props {
  levels: readonly WatcherState[];
  price: number | null;
}

/** Tall enough that six levels clear each other's labels at ~22px apart. */
const HEIGHT = 240;

export default function LevelLadder({ levels, price }: Props) {
  const scale = ladderScale(levels, price);

  // One level and no price is a line with nothing to be relative to. The table
  // already carries every number, so omitting the picture loses nothing.
  if (!scale) return null;

  const ordered = [...levels].sort((a, b) => b.level_price - a.level_price);
  const priceY = price !== null ? scale(price) * HEIGHT : null;

  return (
    <figure className={s.figure}>
      <div className={s.frame} style={{ height: `${HEIGHT}px` }}>
        {/* The axis spine. Recessive by design — it orients, it is not data. */}
        <span className={s.spine} aria-hidden="true" />

        {ordered.map((level) => {
          const look = stateLook(level.state);
          const top = scale(level.level_price) * HEIGHT;
          return (
            <div
              key={level.label}
              className={cx(s.level, s[`tone_${look.tone}`])}
              style={{ top: `${top}px` }}
            >
              <span className={s.levelLabel}>{level.label}</span>
              <span className={s.levelLine} aria-hidden="true" />
              <span className={s.levelPrice}>{formatPrice(level.level_price)}</span>
            </div>
          );
        })}

        {priceY !== null && (
          <div className={s.price} style={{ top: `${priceY}px` }}>
            {/* A 2px surface ring keeps the cursor legible where it crosses a
                level line, rather than the two merging into one thick mark. */}
            <span className={s.priceLine} aria-hidden="true" />
            <span className={s.priceChip}>{formatPrice(price as number)}</span>
          </div>
        )}
      </div>

      <figcaption className={s.caption}>
        Marked levels and last price, to scale. Distance is the point — the table below carries each
        level&apos;s state.
      </figcaption>
    </figure>
  );
}
