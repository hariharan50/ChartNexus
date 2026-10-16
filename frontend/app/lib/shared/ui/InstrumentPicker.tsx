import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react';
import { useInstruments } from '$contexts/instrument-catalog/queries';
import { filterInstruments, toPickerEntries } from '$contexts/instrument-catalog/search';
import type { InstrumentKind } from '$contexts/instrument-catalog/types';
import SymbolAvatar from '$shared/ui/SymbolAvatar';
import { cx } from '$shared/ui/cx';
import IconChevronDown from '$shared/ui/icons/IconChevronDown';
import s from './InstrumentPicker.module.css';

/**
 * Choose the instrument a page charts.
 *
 * Replaces the ‹ › cyclers that walked a hardcoded three. There are ~221
 * contracts, so the list is searchable and grouped — indices first, because
 * they are what most sessions start from, then the stocks under a count so the
 * size of the universe is visible rather than implied.
 *
 * The arrows survive the rewrite because stepping is genuinely useful once you
 * have filtered: type "BANK", then walk the four contracts that match. They
 * step **within what the search shows**, not the whole catalog.
 *
 * Logos come from `SymbolAvatar`, which has a mark for all 213 stocks and none
 * of the indices — those fall back to its generated initials.
 */

interface Props {
  /** The chosen ticker. Not required to be in the catalog — see `current`. */
  value: string;
  onChange: (symbol: string) => void;
  /**
   * Restrict the list. Pass `'index'` only where a page is genuinely
   * index-only; a filter that merely hides a page's own thin data is a lie
   * told with a dropdown.
   */
  kind?: InstrumentKind;
  /** `sidebar` is the settings-panel pill; `field` sits in a horizontal row. */
  variant?: 'sidebar' | 'field';
  className?: string;
}

/** Rows to show at once. The list scrolls; this is the search's cap. */
const MAX_ROWS = 120;

export default function InstrumentPicker({
  value,
  onChange,
  kind,
  variant = 'sidebar',
  className
}: Props) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [active, setActive] = useState(0);

  const root = useRef<HTMLDivElement>(null);
  const search = useRef<HTMLInputElement>(null);
  const listId = useId();

  const { instruments, isLoading } = useInstruments(kind ? { kind } : {});

  const entries = useMemo(() => toPickerEntries(instruments), [instruments]);
  const rows = useMemo(() => filterInstruments(entries, query, MAX_ROWS), [entries, query]);

  // `kind` off the catalog row, so the group headers do not have to re-derive
  // it from the ticker.
  const kindOf = useMemo(() => {
    const map = new Map<string, InstrumentKind>();
    for (const row of instruments) map.set(row.symbol, row.kind);
    return map;
  }, [instruments]);

  const indices = rows.filter((row) => kindOf.get(row.symbol) === 'index');
  const stocks = rows.filter((row) => kindOf.get(row.symbol) !== 'index');

  const current = entries.find((entry) => entry.symbol === value);

  const close = useCallback(() => {
    setOpen(false);
    setQuery('');
    setActive(0);
  }, []);

  const pick = useCallback(
    (symbol: string) => {
      onChange(symbol);
      close();
    },
    [onChange, close]
  );

  /** Walk the filtered list — the arrows are a refinement of the search. */
  const step = useCallback(
    (delta: number) => {
      const pool = rows.length > 0 ? rows : entries;
      if (pool.length === 0) return;
      const at = pool.findIndex((entry) => entry.symbol === value);
      const from = at === -1 ? 0 : at;
      const next = pool[(from + delta + pool.length) % pool.length];
      if (next) onChange(next.symbol);
    },
    [rows, entries, value, onChange]
  );

  useEffect(() => {
    if (!open) return;
    search.current?.focus();
    function onPointerDown(event: PointerEvent) {
      if (!root.current?.contains(event.target as Node)) close();
    }
    document.addEventListener('pointerdown', onPointerDown);
    return () => document.removeEventListener('pointerdown', onPointerDown);
  }, [open, close]);

  function onKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'Escape') {
      event.stopPropagation();
      close();
      return;
    }
    if (rows.length === 0) return;
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      setActive((at) => (at + 1) % rows.length);
      return;
    }
    if (event.key === 'ArrowUp') {
      event.preventDefault();
      setActive((at) => (at - 1 + rows.length) % rows.length);
      return;
    }
    if (event.key === 'Enter') {
      event.preventDefault();
      const chosen = rows[active] ?? rows[0];
      if (chosen) pick(chosen.symbol);
    }
  }

  // One flat index across both groups, so the arrow keys cross the header
  // without the reader having to know there is one.
  const indexOf = (symbol: string) => rows.findIndex((row) => row.symbol === symbol);

  const row = (entry: { symbol: string; name: string }) => {
    const at = indexOf(entry.symbol);
    return (
      <li key={entry.symbol} role="presentation">
        <button
          type="button"
          id={`${listId}-${at}`}
          role="option"
          aria-selected={at === active}
          className={cx(s.row, at === active && s.activeRow, entry.symbol === value && s.chosen)}
          // `onMouseDown`: the search input's blur would otherwise tear the
          // list down before a click could land on it.
          onMouseDown={(event) => {
            event.preventDefault();
            pick(entry.symbol);
          }}
          onMouseEnter={() => setActive(at)}
        >
          <SymbolAvatar symbol={entry.symbol} size={22} />
          <span className={s.ticker}>{entry.symbol}</span>
          <span className={s.company}>{entry.name}</span>
        </button>
      </li>
    );
  };

  return (
    <div className={cx(s.wrap, variant === 'field' && s.field, className)} ref={root}>
      <div className={s.pill}>
        <button
          type="button"
          className={s.trigger}
          aria-haspopup="listbox"
          aria-expanded={open}
          onClick={() => setOpen((was) => !was)}
          title={current?.name ?? value}
        >
          <SymbolAvatar symbol={value} size={22} />
          <span className={s.chosenTicker}>{value}</span>
          <span className={s.caret} aria-hidden="true">
            <IconChevronDown />
          </span>
        </button>
        <span className={s.cyclers}>
          <button type="button" aria-label="Previous instrument" onClick={() => step(-1)}>
            ‹
          </button>
          <button type="button" aria-label="Next instrument" onClick={() => step(1)}>
            ›
          </button>
        </span>
      </div>

      {open ? (
        <div className={s.panel}>
          <input
            ref={search}
            type="text"
            className={s.search}
            placeholder="Search ticker or company"
            aria-label="Search instruments"
            role="combobox"
            aria-expanded
            aria-controls={listId}
            aria-autocomplete="list"
            autoComplete="off"
            value={query}
            onChange={(event) => {
              setQuery(event.currentTarget.value);
              setActive(0);
            }}
            onKeyDown={onKeyDown}
          />

          <ul className={s.list} id={listId} role="listbox" aria-label="Instruments">
            {indices.length > 0 ? (
              <li className={s.group} role="presentation">
                Indices
              </li>
            ) : null}
            {indices.map(row)}

            {stocks.length > 0 ? (
              <li className={s.group} role="presentation">
                Stocks — ({stocks.length})
              </li>
            ) : null}
            {stocks.map(row)}

            {rows.length === 0 ? (
              <li className={s.none}>
                {isLoading ? 'Loading instruments…' : `Nothing matches “${query.trim()}”.`}
              </li>
            ) : null}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
