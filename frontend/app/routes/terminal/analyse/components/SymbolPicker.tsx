import { useEffect, useMemo, useRef, useState } from 'react';
import { cx } from '$shared/ui/cx';
import IconSearch from '$shared/ui/icons/IconSearch';
import type { Instrument } from '../../options/open-interest/oi-data';
import s from './SymbolPicker.module.css';

/**
 * Choose the instrument the workspace charts.
 *
 * A searchable dialog rather than the ‹ › cyclers it replaces: cycling makes
 * you step through instruments you did not want to see, and it does not scale
 * past the three there are today.
 *
 * The focus handling — trap, Escape to close, restore to the opener — is the
 * same contract as `multi-oi-volume/components/ContractPicker`, deliberately.
 * This also sits over a live, polling page, and a second dialog convention in
 * the same app is a second thing to get subtly wrong.
 */
interface Props {
  instruments: Instrument[];
  selected: string;
  onPick: (symbol: string) => void;
  onClose: () => void;
}

export default function SymbolPicker({ instruments, selected, onPick, onClose }: Props) {
  const [query, setQuery] = useState('');
  const dialog = useRef<HTMLDivElement>(null);
  const search = useRef<HTMLInputElement>(null);
  const opener = useRef<Element | null>(null);

  useEffect(() => {
    opener.current = document.activeElement;
    search.current?.focus();
    const restore = opener.current;
    return () => {
      if (restore instanceof HTMLElement) restore.focus();
    };
  }, []);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        event.stopPropagation();
        onClose();
        return;
      }
      if (event.key !== 'Tab') return;

      const focusable = dialog.current?.querySelectorAll<HTMLElement>(
        'input, button, [tabindex]:not([tabindex="-1"])'
      );
      if (!focusable || focusable.length === 0) return;
      const first = focusable[0]!;
      const last = focusable[focusable.length - 1]!;
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
    document.addEventListener('keydown', onKey, true);
    return () => document.removeEventListener('keydown', onKey, true);
  }, [onClose]);

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (needle === '') return instruments;
    return instruments.filter((entry) => entry.short.toLowerCase().includes(needle));
  }, [instruments, query]);

  return (
    <div className={s.backdrop} onPointerDown={onClose}>
      {/* Stop clicks inside from reaching the backdrop's close handler. */}
      <div
        ref={dialog}
        className={s.dialog}
        role="dialog"
        aria-modal="true"
        aria-label="Choose instrument"
        onPointerDown={(event) => event.stopPropagation()}
      >
        <div className={s.searchRow}>
          <span className={s.searchIco} aria-hidden="true">
            <IconSearch />
          </span>
          <input
            ref={search}
            className={s.search}
            type="text"
            placeholder="Search instrument"
            aria-label="Search instrument"
            value={query}
            onChange={(event) => setQuery(event.currentTarget.value)}
          />
        </div>

        <ul className={s.list}>
          {visible.map((entry) => (
            <li key={entry.symbol}>
              <button
                type="button"
                className={cx(s.row, entry.symbol === selected && s.current)}
                aria-current={entry.symbol === selected}
                onClick={() => {
                  onPick(entry.symbol);
                  onClose();
                }}
              >
                <span className={s.badge}>{entry.badge}</span>
                <span className={s.name}>{entry.short}</span>
              </button>
            </li>
          ))}
          {visible.length === 0 ? <li className={s.none}>Nothing matches “{query}”.</li> : null}
        </ul>
      </div>
    </div>
  );
}
