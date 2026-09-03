import { useEffect, useRef } from 'react';
import { seriesColor } from '$shared/charts/options/multi-series';
import { cx } from '$shared/ui/cx';
import { legKey, MAX_PICKS, type Leg, type Side } from '../multistrike-data';
import s from '../route.module.css';

/**
 * The Call / Strike / Put ladder the reader picks contracts off.
 *
 * Both sides of a strike live on one row because that is how a chain is read —
 * a flat list of "23950 CE, 23950 PE, 24000 CE …" makes the reader do the
 * pairing themselves. Each cell is its own button: adding a call says nothing
 * about the put, which is the whole point of a page that can plot either.
 *
 * A picked cell carries its series colour, so the ladder doubles as a legend —
 * the same colour identifies that contract in the chips, the chart and the
 * tooltip.
 */
interface Props {
  strikes: number[];
  /** The at-the-money strike, highlighted; `null` when the chain has no ATM. */
  atm: number | null;
  selected: Leg[];
  onToggle: (leg: Leg) => void;
}

export default function StrikeLadder({ strikes, atm, selected, onToggle }: Props) {
  const full = selected.length >= MAX_PICKS;
  const scroller = useRef<HTMLDivElement>(null);
  const atmRow = useRef<HTMLDivElement>(null);

  /**
   * Open on the money.
   *
   * The ladder is ~50 strikes deep and the interesting end is the middle, so
   * landing at 23000 means every reader scrolls before they can do anything.
   * Centred on the ATM row instead, and only while the reader has not scrolled
   * it themselves — `atm` changes through the session as the money moves, and
   * yanking the list out from under someone mid-pick would be worse than a
   * slightly stale scroll position.
   */
  const centred = useRef(false);
  useEffect(() => {
    if (centred.current || atm == null) return;
    const box = scroller.current;
    const row = atmRow.current;
    if (!box || !row) return;
    box.scrollTop = row.offsetTop - box.clientHeight / 2 + row.clientHeight / 2;
    centred.current = true;
  }, [atm, strikes]);

  return (
    <div className={s.ladder}>
      <div className={s.ladderHead} aria-hidden="true">
        <span>Call</span>
        <span>Strike</span>
        <span>Put</span>
      </div>

      <div className={s.ladderBody} ref={scroller}>
        {strikes.map((strike) => (
          <div
            key={strike}
            className={cx(s.ladderRow, strike === atm && s.atmRow)}
            ref={strike === atm ? atmRow : undefined}
          >
            <Cell strike={strike} side="CE" selected={selected} full={full} onToggle={onToggle} />
            <span className={s.ladderStrike}>{strike}</span>
            <Cell strike={strike} side="PE" selected={selected} full={full} onToggle={onToggle} />
          </div>
        ))}
      </div>

      <p className={s.ladderCount} aria-live="polite">
        {selected.length} of {MAX_PICKS} selected
        {full ? ' — remove one to add another' : ''}
      </p>
    </div>
  );
}

/**
 * One side of one strike: `Add CE` when it is not plotted, `CE ×` in its own
 * series colour when it is.
 */
function Cell({
  strike,
  side,
  selected,
  full,
  onToggle
}: {
  strike: number;
  side: Side;
  selected: Leg[];
  full: boolean;
  onToggle: (leg: Leg) => void;
}) {
  const leg: Leg = { strike, side };
  const index = selected.findIndex((entry) => legKey(entry) === legKey(leg));
  const on = index >= 0;
  const color = on ? seriesColor(index) : undefined;

  return (
    <button
      type="button"
      className={cx(s.ladderCell, side === 'CE' ? s.callCell : s.putCell, on && s.picked)}
      aria-pressed={on}
      aria-label={on ? `Remove ${strike} ${side}` : `Add ${strike} ${side}`}
      disabled={!on && full}
      onClick={() => onToggle(leg)}
      style={
        color === undefined
          ? undefined
          : {
              color,
              borderColor: `color-mix(in srgb, ${color} 45%, transparent)`,
              background: `color-mix(in srgb, ${color} 12%, transparent)`
            }
      }
    >
      {on ? (
        <>
          {side} <span aria-hidden="true">×</span>
        </>
      ) : (
        `Add ${side}`
      )}
    </button>
  );
}
