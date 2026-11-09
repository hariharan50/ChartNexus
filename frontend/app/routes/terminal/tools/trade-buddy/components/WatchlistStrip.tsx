import { cx } from '$shared/ui/cx';
import { stateLook, type Watchable, type WatchRow } from '../trade-buddy-data';
import s from './WatchlistStrip.module.css';

/**
 * All three indices at once, as a segmented tab bar.
 *
 * The page below shows one instrument in full. Without this you would have to
 * cycle the picker to find out that BANKNIFTY had broken a level while you
 * were reading NIFTY — which is exactly the thing the alerts exist to stop you
 * having to do, and it would be odd for the page to reintroduce it.
 *
 * Unmarked indices are listed rather than omitted. An index you forgot to mark
 * produces no alerts all day, and absence is the one state that looks
 * identical to "nothing happened".
 *
 * Compact, and no longer carrying each index's price. The price belongs where
 * the decision is made — beside the levels it is being compared against — and
 * three large numbers across the top competed with the one that matters. What
 * stays is the single line per index that would change what you do: its
 * attention state, or why it has none.
 *
 * The delivery chips sit on the same row rather than in their own band. They
 * answer a question that only matters alongside the watch ("if something
 * happens, will I hear about it?"), and a row of their own would make two
 * strips where the content is one thought.
 */
interface Props {
  rows: readonly WatchRow[];
  selected: Watchable;
  onSelect: (symbol: Watchable) => void;
  /** Rendered to the right of the tabs — delivery state, from the page. */
  chips?: React.ReactNode;
}

export default function WatchlistStrip({ rows, selected, onSelect, chips }: Props) {
  if (rows.length === 0) return null;

  return (
    <div className={s.bar}>
      <div className={s.tabs} role="tablist" aria-label="Watched instruments">
        {rows.map((row) => {
          const active = row.symbol === selected;
          return (
            <button
              key={row.symbol}
              type="button"
              role="tab"
              aria-selected={active}
              className={cx(s.tab, active && s.active)}
              onClick={() => onSelect(row.symbol)}
            >
              <span className={s.symbol}>{row.symbol}</span>
              <span className={s.status}>{status(row)}</span>
            </button>
          );
        })}
      </div>
      {chips ? <div className={s.chips}>{chips}</div> : null}
    </div>
  );
}

/** The one line per index, as a node so each state can carry its own tone. */
function status(row: WatchRow) {
  if (!row.watched) {
    return <span className={s.quiet}>No levels</span>;
  }

  const count = `${row.levels_marked} level${row.levels_marked === 1 ? '' : 's'}`;

  // Stale outranks everything below it. The levels exist and look watched, and
  // nothing is being compared against them — so a state word here would be a
  // lie, however accurate it was yesterday.
  if (row.levels_stale) {
    return <span className={s.warn}>{count} · stale</span>;
  }

  // A degraded band set is worth seeing here, not only in the sensitivity
  // card: it silently changes what every alert on this instrument means.
  const unscaled =
    row.band_source === 'points' ? (
      <span className={s.quiet} title="ATR unavailable — bands are unscaled">
        {' '}
        · unscaled
      </span>
    ) : null;

  if (row.attention) {
    const look = stateLook(row.attention);
    return (
      <span className={s[`tone_${look.tone}`]}>
        {/* Word + glyph, never colour alone. */}
        <span aria-hidden="true">{look.glyph}</span> {look.label}
        {row.nearest_label && row.nearest_distance !== null
          ? ` · ${row.nearest_label} ${row.nearest_distance.toFixed(0)} pts`
          : null}
        {unscaled}
      </span>
    );
  }

  return (
    <span className={s.armed}>
      {count} · armed{unscaled}
    </span>
  );
}
