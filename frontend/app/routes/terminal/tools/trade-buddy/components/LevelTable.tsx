import type { RefObject } from 'react';
import { cx } from '$shared/ui/cx';
import {
  formatPrice,
  gapToNextBelow,
  hasFlipped,
  signedPoints,
  stateLook,
  type DraftLevel,
  type LevelRole,
  type WatcherState
} from '../trade-buddy-data';
import s from './LevelTable.module.css';

/**
 * The six levels, once: editable, and carrying what the watcher makes of them.
 *
 * This replaces three separate renderings of the same six prices — a form, a
 * ladder and a read-only state table. Editing the price *in* the row that
 * shows its state is the whole point: the question "should R1 be at 24,700?"
 * is answered by what R1 has been doing all morning, and that answer used to
 * be in a different panel.
 *
 * Rows are ordered by price, descending, which is the order they appear on a
 * chart. Blank slots keep their slot order at the end rather than sorting as
 * zero, so the form does not reshuffle while a price is half-typed.
 */
interface Row {
  draft: DraftLevel;
  /** The slot's index in the draft; `-1` for a level with no editable slot. */
  index: number;
  /** The engine's view of this level, when it has one. */
  live: WatcherState | undefined;
  /** The saved price, to tell an edited row from a clean one. */
  saved: string;
}

interface Props {
  draft: readonly DraftLevel[];
  saved: readonly DraftLevel[];
  live: readonly WatcherState[];
  price: number | null;
  /** Bars drawn per level. Follows the cap so "2 of 3 left" is countable. */
  dailyCap: number;
  /** Stale marks are watched by nobody, so no row claims a live state. */
  stale: boolean;
  onChange: (index: number, price: string) => void;
  firstPriceRef: RefObject<HTMLInputElement | null>;
}

export default function LevelTable({
  draft,
  saved,
  live,
  price,
  dailyCap,
  stale,
  onChange,
  firstPriceRef
}: Props) {
  const liveByLabel = new Map(live.map((level) => [level.label.toUpperCase(), level]));
  const savedByLabel = new Map(saved.map((row) => [row.label.toUpperCase(), row.price]));

  const rows: Row[] = draft.map((row, index) => ({
    draft: row,
    index,
    live: liveByLabel.get(row.label.toUpperCase()),
    saved: savedByLabel.get(row.label.toUpperCase()) ?? ''
  }));

  // A level the watcher holds that has no slot to edit it in. Two ways to get
  // here, and both must be visible: the API accepts twelve marks with any
  // labels while this form offers six fixed ones, and the levels query can
  // fail or lag behind the state query, leaving a blank form beside a running
  // watch. Dropping these rows would have the page report six Skipped levels
  // while six are actually being watched — a silence that looks deliberate.
  const slots = new Set(draft.map((row) => row.label.toUpperCase()));
  const extra: Row[] = live
    .filter((level) => !slots.has(level.label.toUpperCase()))
    .map((level) => ({
      draft: { label: level.label, role: level.role, price: String(level.level_price) },
      index: -1,
      live: level,
      saved: String(level.level_price)
    }));

  const all = [...rows, ...extra];
  // A row is placed by whatever price it has: the typed one if there is one,
  // otherwise the watcher's. Sorting a watched level as blank would drop it to
  // the bottom of a table ordered by price.
  const filled = all
    .filter((row) => rowPrice(row) !== null)
    .sort((a, b) => (rowPrice(b) as number) - (rowPrice(a) as number));
  const blank = all.filter((row) => rowPrice(row) === null);
  const ordered = [...filled, ...blank];

  const prices = filled.map((row) => rowPrice(row) as number);
  // Where the LTP divider goes: after the last filled row still above price.
  const dividerAfter =
    price === null ? -1 : filled.filter((row) => (rowPrice(row) as number) > price).length - 1;
  const above = price === null ? [] : filled.filter((row) => (rowPrice(row) as number) > price);
  const below = price === null ? [] : filled.filter((row) => (rowPrice(row) as number) <= price);

  // The first *slot*, not the first displayed row. Both callers reach for this
  // ref at a moment when the form is empty — the empty state's button, and
  // "re-mark" straight after clearing — and when it is empty the display order
  // is the slot order. Taking `ordered[0]` instead would hand back whichever
  // row happened to have the highest price before the clear, because the focus
  // call runs before React has re-rendered the new order.
  const firstIndex = 0;

  return (
    <div className={s.scroller}>
      <table className={s.table}>
        <caption className={s.srOnly}>
          Each marked level: its price, how far it is from the last traded price, what it is
          currently acting as, what the watcher has seen, and how many alerts it has left today
        </caption>
        <thead>
          <tr>
            <th scope="col">Level</th>
            <th scope="col">Price</th>
            <th scope="col" className={s.numeric}>
              {price === null ? 'Gap below' : 'From LTP'}
            </th>
            <th scope="col">Acting as</th>
            <th scope="col">State</th>
            <th scope="col">Alerts left</th>
          </tr>
        </thead>
        <tbody>
          {ordered.map((row, position) => (
            <LevelRow
              key={row.draft.label}
              row={row}
              price={price}
              prices={prices}
              dailyCap={dailyCap}
              stale={stale}
              onChange={onChange}
              inputRef={row.index === firstIndex ? firstPriceRef : undefined}
              divider={
                position === dividerAfter ? (
                  <Divider
                    price={price as number}
                    above={above[above.length - 1]?.draft.label}
                    below={below[0]?.draft.label}
                  />
                ) : null
              }
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}

interface RowProps {
  row: Row;
  price: number | null;
  prices: readonly number[];
  dailyCap: number;
  stale: boolean;
  onChange: (index: number, price: string) => void;
  inputRef: RefObject<HTMLInputElement | null> | undefined;
  divider: React.ReactNode;
}

function LevelRow({ row, price, prices, dailyCap, stale, onChange, inputRef, divider }: RowProps) {
  const { draft, live } = row;
  const value = draft.price.trim();
  const readOnly = row.index === -1;
  // "Nothing here" means neither a typed price nor a watched level. A blank
  // field beside a live level is not an empty slot, it is a pending deletion —
  // and the row still has to report what that level is doing until it is saved.
  const isBlank = value === '' && live === undefined;
  const edited = !readOnly && value !== row.saved.trim();
  // The live role when there is one: a broken R1 is acting as support, and the
  // slot's own role would keep insisting it is resistance.
  const role: LevelRole = live?.role ?? draft.role;
  const look = live ? stateLook(live.state) : null;
  const active =
    !stale &&
    live !== undefined &&
    (live.state === 'approaching' || live.state === 'touched' || live.state === 'break_pending');

  return (
    <>
      <tr className={cx(active && s.active)}>
        <th scope="row" className={s.levelCell}>
          <span className={cx(s.chip, role === 'support' ? s.chipSupport : s.chipResistance)}>
            {draft.label}
          </span>
          {live && hasFlipped(live) && <span className={s.flip}>flipped</span>}
        </th>

        <td>
          {readOnly ? (
            <span className={s.readOnly} title="Marked outside this form — not editable here">
              {formatPrice(live?.level_price ?? 0)}
            </span>
          ) : (
            <input
              ref={inputRef}
              className={cx(s.input, edited && s.inputEdited)}
              type="number"
              inputMode="decimal"
              step="0.05"
              min="0"
              placeholder="Skip"
              aria-label={`${draft.label} price`}
              value={draft.price}
              onChange={(event) => onChange(row.index, event.target.value)}
            />
          )}
        </td>

        <td className={s.numeric}>
          <span className={s.distance}>{distance(rowPrice(row), price, prices)}</span>
        </td>

        <td>
          {isBlank ? (
            <span className={s.muted}>—</span>
          ) : (
            <span className={s.role}>
              <span
                className={cx(s.dot, role === 'support' ? s.dotSupport : s.dotResistance)}
                aria-hidden="true"
              />
              {role}
            </span>
          )}
        </td>

        <td>
          {/* Glyph + word, never colour alone: this has to survive greyscale,
              colour-vision deficiency and forced-colours. The live state wins
              over the draft wherever both exist — what the watcher is doing is
              a fact, and what has been typed is not yet one. */}
          {stale && live ? (
            <span
              className={cx(s.state, s.tone_neutral)}
              title="Levels are from an earlier session"
            >
              <span aria-hidden="true">·</span> Paused
            </span>
          ) : look ? (
            <span className={cx(s.state, s[`tone_${look.tone}`])}>
              <span aria-hidden="true">{look.glyph}</span> {look.label}
            </span>
          ) : isBlank ? (
            <span className={cx(s.state, s.tone_skipped)}>Skipped</span>
          ) : (
            <span className={cx(s.state, s.tone_skipped)}>Not saved</span>
          )}
        </td>

        <td>
          {!live || stale ? (
            <span className={s.muted}>—</span>
          ) : (
            <AlertBars remaining={live.alerts_remaining} cap={dailyCap} />
          )}
        </td>
      </tr>
      {divider}
    </>
  );
}

/**
 * Where price sits in the ladder, as a row of its own.
 *
 * The table is sorted by price, so price itself has a place in that order —
 * and putting it there answers "which levels are above me" without the reader
 * having to compare six numbers against a seventh one in the header.
 */
function Divider({
  price,
  above,
  below
}: {
  price: number;
  above: string | undefined;
  below: string | undefined;
}) {
  const between =
    above && below ? `between ${above} and ${below}` : above ? `below ${above}` : `above ${below}`;
  return (
    <tr className={s.dividerRow}>
      <th scope="row" className={s.levelCell}>
        <span className={cx(s.chip, s.chipPrice)}>LTP</span>
      </th>
      <td className={s.dividerPrice}>{formatPrice(price)}</td>
      <td colSpan={4} className={s.dividerNote}>
        <span className={s.rule} aria-hidden="true" />
        {between}
      </td>
    </tr>
  );
}

/**
 * Observation alerts left for this level today, as bars.
 *
 * A bar per alert rather than a number, because the useful reading is "nearly
 * out" and that is a shape, not an arithmetic comparison against a cap the
 * reader would have to remember. Confirmed breaks ignore the cap entirely,
 * which is why an empty row is not the same as "this level has gone silent".
 */
function AlertBars({ remaining, cap }: { remaining: number; cap: number }) {
  const total = Math.max(cap, remaining, 3);
  return (
    <span className={s.bars} aria-label={`${remaining} of ${cap} alerts left`} role="img">
      {Array.from({ length: total }, (_, i) => (
        <span key={i} className={cx(s.bar, i < remaining && s.barFilled)} aria-hidden="true" />
      ))}
    </span>
  );
}

/**
 * The price a row sits at: what has been typed, else what is being watched.
 *
 * Null only when there is neither. Returned as a number so the sort, the
 * divider and the distance column all place a row the same way — three
 * separate readings of "which price is this row at" would eventually disagree
 * and put the LTP divider on the wrong side of a level.
 */
function rowPrice(row: Row): number | null {
  const typed = row.draft.price.trim();
  if (typed !== '') {
    const value = Number(typed);
    if (Number.isFinite(value) && value > 0) return value;
  }
  return row.live?.level_price ?? null;
}

/**
 * The third column: distance from price, or the gap to the level below.
 *
 * Two different measures in one column on purpose. Before the first tick there
 * is no distance to show and the useful thing about a set of marks is how far
 * apart they are — which is the one question a column of prices cannot answer.
 */
function distance(level: number | null, price: number | null, prices: readonly number[]): string {
  if (level === null) return '—';
  if (price !== null) return signedPoints(level - price);
  const gap = gapToNextBelow(level, prices);
  return gap === null ? '—' : `${gap.toFixed(0)} pts`;
}
