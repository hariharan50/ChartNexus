import type { ReactNode } from 'react';
import { useMemo } from 'react';
import SymbolAvatar from '$shared/ui/SymbolAvatar';
import { cx } from '$shared/ui/cx';
import s from './DivergingBoard.module.css';

/** One name on one side of the board. */
export interface BoardRow {
  symbol: string;
  /** Signed. Its magnitude sets the bar, its sign picks the side. */
  value: number;
  /** The full figures, for the bar's hover. */
  hover: string;
}

/** A row of the board: the n-th riser and the n-th faller, side by side. */
export interface PairedRow {
  up: BoardRow | null;
  down: BoardRow | null;
}

interface Props {
  title: string;
  /** Sits opposite the title — the two aggregates, acting as the legend. */
  totals?: ReactNode;
  note?: ReactNode;
  hint?: ReactNode;
  /** Positive movers, biggest first. */
  up: BoardRow[];
  /** Negative movers, most negative first. */
  down: BoardRow[];
  format: (value: number) => string;
}

/**
 * Two ranked lists meeting at one axis.
 *
 * A centred diverging board: risers rank down the left, fallers down the
 * right, and the bars meet on **one shared scale** — so a bar twice as long
 * really is twice the value, whichever side of the centre it is on.
 *
 * **Rows are rank-paired, not related.** Line one carries the biggest riser
 * and the biggest faller, and those are two unrelated companies. The centre
 * gutter and the per-bar hover keep that from reading as a pairing.
 *
 * Shared by the index-points board and the change-% board rather than copied:
 * they are the same picture of two different measures, and two copies of this
 * much geometry drift apart within a week.
 */
export default function DivergingBoard({ title, totals, note, hint, up, down, format }: Props) {
  const rows = useMemo(() => pairRows(up, down), [up, down]);
  const scale = useMemo(() => sharedScale(up, down), [up, down]);

  return (
    <section className={s.card}>
      <div className={s.head}>
        <h2 className={s.title}>{title}</h2>
        {totals ? <p className={s.totals}>{totals}</p> : null}
      </div>
      {note ? <p className={s.note}>{note}</p> : null}

      {/*
        Hidden from the accessibility tree on purpose. Read aloud, a row would
        announce two unrelated companies as if they were a pair, and every
        name here is listed elsewhere on the page. Nothing is gated by it.
      */}
      <div className={s.rows} aria-hidden="true">
        {rows.map((row) => (
          <div className={s.row} key={row.up?.symbol ?? row.down?.symbol}>
            <Side row={row.up} scale={scale} side="up" format={format} />
            <Side row={row.down} scale={scale} side="down" format={format} />
          </div>
        ))}
      </div>

      {hint ? <p className={s.hint}>{hint}</p> : null}
    </section>
  );
}

/**
 * One half of a row: the label and the bar, mirrored about the centre.
 *
 * The bar grows away from the centre axis toward its own label, so length is
 * read outwards from a common origin on both sides.
 */
function Side({
  row,
  scale,
  side,
  format
}: {
  row: BoardRow | null;
  scale: number;
  side: 'up' | 'down';
  format: (value: number) => string;
}) {
  // The empty half of a ragged row still occupies its columns, or every row
  // below the shorter list slides across the centre axis.
  if (row === null) {
    return side === 'up' ? (
      <>
        <span className={cx(s.label, s.up)} />
        <span className={cx(s.track, s.up)} />
      </>
    ) : (
      <>
        <span className={cx(s.track, s.down)} />
        <span className={cx(s.label, s.down)} />
      </>
    );
  }

  const name = (
    <>
      <SymbolAvatar symbol={row.symbol} size={20} />
      <span className={s.symbol}>{row.symbol}</span>
    </>
  );

  const label = (
    <span className={cx(s.label, s[side])}>
      {side === 'up' ? name : null}
      <span className={cx(s.points, s[side])}>{format(row.value)}</span>
      {side === 'down' ? name : null}
    </span>
  );

  const track = (
    <span className={cx(s.track, s[side])}>
      <span
        className={cx(s.bar, s[side])}
        style={{ width: barWidth(row.value, scale) }}
        title={row.hover}
      />
    </span>
  );

  // Mirrored, and this order is the whole layout: label-then-track on the
  // left, track-then-label on the right, so the two tracks are the middle two
  // columns and the bars meet at one axis. Emit them the same way round on
  // both sides and the right-hand bars end up against the far margin with a
  // gap where the centre should be.
  return side === 'up' ? (
    <>
      {label}
      {track}
    </>
  ) : (
    <>
      {track}
      {label}
    </>
  );
}

/* -- the arithmetic --------------------------------------------------------- */

/**
 * Rank-pair the two sides into rows, longest list setting the length.
 *
 * The lists are ragged — a market usually has far more names up than down —
 * and the tail rows carry one bar and an empty label rather than being
 * dropped: those names moved, and a board claiming to show the whole scope
 * has to show them.
 */
export function pairRows(up: BoardRow[], down: BoardRow[]): PairedRow[] {
  const length = Math.max(up.length, down.length);
  return Array.from({ length }, (_, index) => ({
    up: up[index] ?? null,
    down: down[index] ?? null
  }));
}

/**
 * The value one full-width bar stands for, shared by both sides.
 *
 * One scale, not one per side. Scaling each side to its own maximum would draw
 * the biggest faller as long as the biggest riser, which is the opposite of
 * what this board is for — on a day the scope rose, the red side *should* look
 * shorter.
 */
export function sharedScale(up: BoardRow[], down: BoardRow[]): number {
  const largest = (rows: BoardRow[]) =>
    rows.reduce((peak, row) => Math.max(peak, Math.abs(row.value)), 0);
  // Never zero: a board where nothing moved still has to divide by something.
  return Math.max(largest(up), largest(down), Number.EPSILON);
}

/**
 * A bar's width as a CSS length.
 *
 * A move too small to round to a pixel still gets a 2px sliver, so a name that
 * ticked a hundredth of a percent reads as "present but tiny" rather than as
 * absent. An exact zero draws nothing, because it is.
 */
function barWidth(value: number, scale: number): string {
  if (value === 0) return '0';
  return `max(2px, ${((Math.abs(value) / scale) * 100).toFixed(2)}%)`;
}
