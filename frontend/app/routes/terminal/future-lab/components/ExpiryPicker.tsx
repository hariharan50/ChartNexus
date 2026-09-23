import { useEffect, useMemo } from 'react';
import type { ExpiryOption } from '$contexts/futures-analytics/types';
import { useFuturesExpiriesQuery } from '$contexts/futures-analytics/queries';
import { expiryLabel } from '../heatmap-data';
import s from './ExpiryPicker.module.css';

const EMPTY: ExpiryOption[] = [];

interface Props {
  /** The selected series: 0 near month, 1 next, 2 far. */
  series: number;
  onSeries: (series: number) => void;
  /**
   * The expiry the board actually came back with, when it is known. Preferred
   * over the picker's own label for the selected row: it is the date those
   * rows really belong to, and the listing's is only the universe's modal one.
   */
  resolved?: string | null | undefined;
  /**
   * Whether the board that came back for this series carries open interest.
   * From the board response, never from the listing: whether a series has it
   * depends on the provider that answered — the generator supplies it with
   * every quote, a live broker only where the sweep has reached — so this is
   * the one answer that cannot disagree with the rows on screen.
   */
  hasOpenInterest?: boolean | undefined;
  /** Hides the caption where the surrounding toolbar already prints one. */
  bare?: boolean;
}

/**
 * Which contract the Future Lab is looking at.
 *
 * **Series, not date.** The value is an index — 0 near month, 1 next, 2 far —
 * because expiry dates do not agree across the universe: NSE and BSE settle on
 * different days and a holiday-shifted name differs from its neighbours, so no
 * one date could name the same contract for every row on a board. The dates
 * here are labels, and the selected option prefers the board's own `expiry`
 * over the listing's so the control cannot disagree with the rows beneath it.
 *
 * Shared by every board page rather than reimplemented: Dashboard, Market
 * Movers, Stocks and the Heatmap are four views of one board, and a picker
 * that offered different expiries on each would be worse than none.
 */
export default function ExpiryPicker({
  series,
  onSeries,
  resolved,
  hasOpenInterest,
  bare = false
}: Props) {
  const query = useFuturesExpiriesQuery();
  // Memoised so the fallback array is not a fresh identity on every render,
  // which would re-run the effect below forever.
  const options = useMemo(() => query.data?.expiries ?? EMPTY, [query.data]);

  // A series can stop being listed — the near month expires and the list
  // shifts down — which would otherwise leave the control pointing at nothing
  // while the board quietly served the furthest contract it had.
  useEffect(() => {
    if (options.length > 0 && !options.some((option) => option.series === series)) {
      onSeries(options[options.length - 1]!.series);
    }
  }, [options, series, onSeries]);

  // Before the list arrives there is nothing honest to offer, so the control
  // shows the contract the board is on rather than an empty dropdown.
  if (options.length === 0) {
    return (
      <div className={s.picker}>
        {bare ? null : <span className={s.caption}>Expiry</span>}
        <span className={s.chip}>{expiryLabel(resolved)}</span>
      </div>
    );
  }

  return (
    <div className={s.picker}>
      {bare ? null : (
        <span className={s.caption} id="expiry-caption">
          Expiry
        </span>
      )}
      <select
        className={s.select}
        value={series}
        aria-label="Contract expiry"
        onChange={(event) => onSeries(Number(event.currentTarget.value))}
      >
        {options.map((option) => (
          <option key={option.series} value={option.series}>
            {labelFor(option, option.series === series ? resolved : null)}
          </option>
        ))}
      </select>
      {hasOpenInterest === false ? (
        // Said once, here, beside the control that caused it. The build-up
        // columns on this series are empty because the background sweep does
        // not reach it — not because the market is flat, and the reader has no
        // way to tell those apart from the board alone.
        <span
          className={s.warn}
          title="Nothing has measured open interest on this contract, so no row can be classified"
        >
          no OI
        </span>
      ) : null}
    </div>
  );
}

/** `27 Oct 2026 (34d)` — the contract and how long it has left. */
function labelFor(option: ExpiryOption, resolved: string | null | undefined): string {
  return expiryLabel(resolved ?? option.expiry);
}
