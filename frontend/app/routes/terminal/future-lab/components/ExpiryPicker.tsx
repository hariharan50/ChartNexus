import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useFuturesExpiriesQuery } from '$contexts/futures-analytics/queries';
import type { ExpiryOption } from '$contexts/futures-analytics/types';
import { cx } from '$shared/ui/cx';
import IconCheck from '$shared/ui/icons/IconCheck';
import IconChevronDown from '$shared/ui/icons/IconChevronDown';
import { expiryLabel, expiryParts } from '../heatmap-data';
import s from './ExpiryPicker.module.css';

const EMPTY: ExpiryOption[] = [];

/**
 * What each series is called. The exchange lists three monthly contracts and
 * a trader names them by position, not by date — "I'm in the near month" —
 * so the list says both.
 */
const SERIES_NAMES = ['Near month', 'Next month', 'Far month'];

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
 * **A listbox, not a `<select>`.** The native control hands its popup to the
 * operating system, which draws it in the OS palette — a white sheet with a
 * blue highlight over a dark terminal, in a font and a row height nothing else
 * on the page shares. It also cannot show what this list wants to show: the
 * date, the days left and the contract's position, in three aligned columns.
 * The keyboard contract is the platform one, so nothing is lost in the trade.
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

  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const list = useRef<HTMLUListElement>(null);

  const close = useCallback(
    (restoreFocus: boolean) => {
      setOpen(false);
      if (restoreFocus) trigger.current?.focus();
    },
    [setOpen]
  );

  // A series can stop being listed — the near month expires and the list
  // shifts down — which would otherwise leave the control pointing at nothing
  // while the board quietly served the furthest contract it had.
  useEffect(() => {
    if (options.length > 0 && !options.some((option) => option.series === series)) {
      onSeries(options[options.length - 1]!.series);
    }
  }, [options, series, onSeries]);

  // Pointer down rather than click: a click that starts inside the popup and
  // ends outside it is a drag-select of a date, not a dismissal.
  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: PointerEvent) {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener('pointerdown', onPointerDown);
    return () => document.removeEventListener('pointerdown', onPointerDown);
  }, [open]);

  // Focus lands on the selected row when the list opens, so the keyboard user
  // starts where the mouse user is already looking.
  useEffect(() => {
    if (!open) return;
    const active = list.current?.querySelector<HTMLElement>('[aria-selected="true"]');
    (active ?? list.current?.querySelector<HTMLElement>('[role="option"]'))?.focus();
  }, [open]);

  function onListKeyDown(event: React.KeyboardEvent<HTMLUListElement>) {
    const items = Array.from(list.current?.querySelectorAll<HTMLElement>('[role="option"]') ?? []);
    const at = items.indexOf(document.activeElement as HTMLElement);

    switch (event.key) {
      case 'Escape':
        event.stopPropagation();
        close(true);
        return;
      case 'Tab':
        // Tab moves on rather than cycling inside: this is a three-row menu,
        // not a dialog, and trapping focus in it would be a trap.
        setOpen(false);
        return;
      case 'ArrowDown':
        event.preventDefault();
        items[Math.min(at + 1, items.length - 1)]?.focus();
        return;
      case 'ArrowUp':
        event.preventDefault();
        items[Math.max(at - 1, 0)]?.focus();
        return;
      case 'Home':
        event.preventDefault();
        items[0]?.focus();
        return;
      case 'End':
        event.preventDefault();
        items[items.length - 1]?.focus();
        return;
      default:
    }
  }

  // The build-up columns on this series are empty because nothing measured
  // open interest for it — not because the market is flat, and the reader has
  // no way to tell those apart from the board alone. It comes from the board,
  // so it is said whether or not the expiry listing has arrived.
  const warning =
    hasOpenInterest === false ? (
      <span
        className={s.warn}
        title="Nothing has measured open interest on this contract, so no row can be classified"
      >
        no OI
      </span>
    ) : null;

  // Before the list arrives there is nothing honest to offer, so the control
  // shows the contract the board is on rather than an empty dropdown.
  if (options.length === 0) {
    return (
      <div className={s.picker}>
        {bare ? null : <span className={s.caption}>Expiry</span>}
        <span className={s.chip}>{expiryLabel(resolved)}</span>
        {warning}
      </div>
    );
  }

  const selected = options.find((option) => option.series === series);

  return (
    <div className={s.picker} ref={root}>
      {bare ? null : <span className={s.caption}>Expiry</span>}

      <div className={s.anchor}>
        <button
          ref={trigger}
          type="button"
          className={cx(s.trigger, open && s.triggerOpen)}
          aria-haspopup="listbox"
          aria-expanded={open}
          aria-label="Contract expiry"
          onClick={() => setOpen((was) => !was)}
          onKeyDown={(event) => {
            if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
              event.preventDefault();
              setOpen(true);
            }
          }}
        >
          <span className={s.triggerDate}>{expiryLabel(resolved ?? selected?.expiry ?? null)}</span>
          <span className={cx(s.caret, open && s.caretOpen)} aria-hidden="true">
            <IconChevronDown />
          </span>
        </button>

        {open ? (
          <ul
            ref={list}
            className={s.list}
            role="listbox"
            aria-label="Contract expiry"
            onKeyDown={onListKeyDown}
          >
            {options.map((option) => {
              const isSelected = option.series === series;
              const { date, days } = expiryParts(
                isSelected ? (resolved ?? option.expiry) : option.expiry
              );
              return (
                <li
                  key={option.series}
                  role="option"
                  tabIndex={-1}
                  aria-selected={isSelected}
                  className={cx(s.option, isSelected && s.optionOn)}
                  onClick={() => {
                    onSeries(option.series);
                    close(true);
                  }}
                  onKeyDown={(event) => {
                    if (event.key !== 'Enter' && event.key !== ' ') return;
                    event.preventDefault();
                    onSeries(option.series);
                    close(true);
                  }}
                >
                  <span className={s.tick} aria-hidden="true">
                    {isSelected ? <IconCheck /> : null}
                  </span>
                  <span className={s.optionDate}>{date}</span>
                  <span className={s.optionDays}>{days === null ? '' : `${days}d`}</span>
                  <span className={s.optionName}>
                    {SERIES_NAMES[option.series] ?? `Series ${option.series + 1}`}
                  </span>
                </li>
              );
            })}
          </ul>
        ) : null}
      </div>

      {warning}
    </div>
  );
}
