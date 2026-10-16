import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router';
import { useInstruments } from '$contexts/instrument-catalog/queries';
import {
  destinationFor,
  filterInstruments,
  toPickerEntries
} from '$contexts/instrument-catalog/search';
import type { Instrument } from '$contexts/instrument-catalog/types';
import { cx } from '$shared/ui/cx';
import IconSearch from '$shared/ui/icons/IconSearch';
import s from './SymbolSearch.module.css';

/**
 * The header's symbol search.
 *
 * Type a ticker or a company name, pick a row, land on that instrument's Price
 * vs OI. Where "that page" is depends on what was picked — see
 * `destinationFor`.
 *
 * **Filtering is local.** The catalog is ~220 rows fetched once and cached for
 * the session (`useInstruments`), so every keystroke is a pure function over an
 * array in memory. There is no debounce here because there is no request to
 * debounce, and a per-keystroke `?search=` round trip would be slower and
 * noisier for a list this size.
 *
 * The catalog fetch is deferred until the box is first focused: this is
 * mounted on every terminal page and most visits never search, so the request
 * should not be part of every page load. Focus is early enough that the rows
 * are there before anyone finishes typing.
 */

/** Rows in the dropdown. Enough to choose from without becoming a page. */
const MAX_ROWS = 8;

export default function SymbolSearch() {
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  // The catalog is wanted from the first focus onward, not just while open —
  // re-disabling it on blur would throw away the fetch mid-flight.
  const [wanted, setWanted] = useState(false);

  const root = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const listId = useId();

  const { instruments, isLoading } = useInstruments({ enabled: wanted });

  const entries = useMemo(() => toPickerEntries(instruments), [instruments]);
  const rows = useMemo(
    () => (query.trim() ? filterInstruments(entries, query, MAX_ROWS) : []),
    [entries, query]
  );

  // The catalog is the authority on `kind`, and the picker entries drop it.
  const bySymbol = useMemo(() => {
    const map = new Map<string, Instrument>();
    for (const entry of instruments) map.set(entry.symbol, entry);
    return map;
  }, [instruments]);

  const close = useCallback(() => {
    setOpen(false);
    setActive(0);
  }, []);

  const go = useCallback(
    (symbol: string) => {
      const instrument = bySymbol.get(symbol);
      if (!instrument) return;
      close();
      setQuery('');
      input.current?.blur();
      void navigate(destinationFor(instrument));
    },
    [bySymbol, close, navigate]
  );

  // Dismiss on an outside click. The header's own `closeMenus` only knows how
  // to shut a `<details>`, and this is not one.
  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: PointerEvent) {
      if (!root.current?.contains(event.target as Node)) close();
    }
    document.addEventListener('pointerdown', onPointerDown);
    return () => document.removeEventListener('pointerdown', onPointerDown);
  }, [open, close]);

  function onKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'Escape') {
      // Keep focus in the box: Escape means "not that list", not "give up".
      close();
      return;
    }
    if (event.key === 'Tab') {
      close();
      return;
    }
    if (!open || rows.length === 0) {
      // Enter with nothing to choose from must not submit anything.
      if (event.key === 'Enter') event.preventDefault();
      return;
    }
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      setActive((current) => (current + 1) % rows.length);
      return;
    }
    if (event.key === 'ArrowUp') {
      event.preventDefault();
      setActive((current) => (current - 1 + rows.length) % rows.length);
      return;
    }
    if (event.key === 'Enter') {
      event.preventDefault();
      // Defaults to the top hit, which is what someone who typed a full ticker
      // and hit Enter without looking down is asking for.
      const chosen = rows[active] ?? rows[0];
      if (chosen) go(chosen.symbol);
    }
  }

  const expanded = open && query.trim().length > 0;

  return (
    <div className={s.wrap} ref={root}>
      <div className={s.search} role="search">
        <span className={s.searchIco} aria-hidden="true">
          <IconSearch />
        </span>
        <input
          ref={input}
          type="text"
          className={s.input}
          placeholder="Search symbol…"
          aria-label="Search symbol"
          role="combobox"
          aria-expanded={expanded}
          aria-controls={listId}
          aria-autocomplete="list"
          {...(expanded && rows[active] ? { 'aria-activedescendant': `${listId}-${active}` } : {})}
          autoComplete="off"
          value={query}
          onFocus={() => {
            setWanted(true);
            setOpen(true);
          }}
          onChange={(event) => {
            setQuery(event.currentTarget.value);
            setOpen(true);
            setActive(0);
          }}
          onKeyDown={onKeyDown}
        />
      </div>

      {expanded ? (
        <div className={s.panel}>
          <ul className={s.list} id={listId} role="listbox" aria-label="Matching instruments">
            {rows.map((entry, index) => (
              <li key={entry.symbol} role="presentation">
                <button
                  type="button"
                  id={`${listId}-${index}`}
                  role="option"
                  aria-selected={index === active}
                  className={cx(s.row, index === active && s.current)}
                  // `onMouseDown` rather than `onClick`: the input's blur would
                  // otherwise close the panel before the click landed.
                  onMouseDown={(event) => {
                    event.preventDefault();
                    go(entry.symbol);
                  }}
                  onMouseEnter={() => setActive(index)}
                >
                  <span className={s.badge}>{entry.badge}</span>
                  <span className={s.name}>{entry.symbol}</span>
                  <span className={s.company}>{entry.name}</span>
                </button>
              </li>
            ))}
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
