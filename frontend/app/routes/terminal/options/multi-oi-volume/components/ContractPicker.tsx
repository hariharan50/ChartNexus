import { useEffect, useMemo, useRef, useState } from 'react';
import { cx } from '$shared/ui/cx';
import { contractLabel, fmtOi, type ContractSeries } from '../multi-oi-data';
import s from './ContractPicker.module.css';

/**
 * Hand-pick which contracts the charts plot.
 *
 * A modal rather than an inline list because the ladder runs to ~80 contracts —
 * far more than the sidebar can hold, and choosing among them is a task in its
 * own right rather than a glance.
 *
 * Focus is trapped and restored, and Escape closes: this sits over a live,
 * polling page, so leaving focus behind in the background would let a keyboard
 * user tab into a chart they cannot see.
 */
interface Props {
  contracts: ContractSeries[];
  selected: string[];
  title: string;
  onApply: (ids: string[]) => void;
  onClose: () => void;
}

type SideFilter = 'all' | 'CE' | 'PE';

/** More lines than this and the chart stops being readable. */
const MAX_PICKS = 10;

export default function ContractPicker({ contracts, selected, title, onApply, onClose }: Props) {
  const [query, setQuery] = useState('');
  const [side, setSide] = useState<SideFilter>('all');
  const [picks, setPicks] = useState<string[]>(selected);
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

      // Keep Tab inside the dialog. Without this the next stop is the page
      // behind the backdrop, which is still polling and redrawing.
      const focusable = dialog.current?.querySelectorAll<HTMLElement>(
        'input, button, select, [tabindex]:not([tabindex="-1"])'
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
    const needle = query.trim();
    return contracts.filter((contract) => {
      if (side !== 'all' && contract.option_type !== side) return false;
      return needle === '' || String(contract.strike).includes(needle);
    });
  }, [contracts, query, side]);

  const full = picks.length >= MAX_PICKS;

  function toggle(id: string) {
    setPicks((current) =>
      current.includes(id)
        ? current.filter((value) => value !== id)
        : current.length >= MAX_PICKS
          ? current
          : [...current, id]
    );
  }

  return (
    <div className={s.backdrop} onPointerDown={onClose}>
      {/* Stop clicks inside from reaching the backdrop's close handler. */}
      <div
        className={s.dialog}
        ref={dialog}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onPointerDown={(event) => event.stopPropagation()}
      >
        <header className={s.head}>
          <h2 className={s.title}>{title}</h2>
          <button type="button" className={s.close} onClick={onClose} aria-label="Close">
            ×
          </button>
        </header>

        <div className={s.filters}>
          <input
            ref={search}
            className={s.search}
            type="search"
            inputMode="numeric"
            placeholder="Search strike…"
            value={query}
            onChange={(event) => setQuery(event.currentTarget.value)}
            aria-label="Search strike"
          />
          <div className={s.sides}>
            {(['all', 'CE', 'PE'] as const).map((value) => (
              <button
                key={value}
                type="button"
                className={cx(s.side, side === value && s.active)}
                onClick={() => setSide(value)}
                aria-pressed={side === value}
              >
                {value === 'all' ? 'All' : value}
              </button>
            ))}
          </div>
        </div>

        <p className={s.count} aria-live="polite">
          {picks.length} of {MAX_PICKS} selected
          {full ? ' — remove one to add another' : ''}
        </p>

        <ul className={s.list}>
          {visible.map((contract) => {
            const on = picks.includes(contract.id);
            return (
              <li key={contract.id}>
                <button
                  type="button"
                  className={cx(s.row, on && s.on)}
                  onClick={() => toggle(contract.id)}
                  aria-pressed={on}
                  disabled={!on && full}
                >
                  <span className={s.name}>{contractLabel(contract)}</span>
                  <span className={s.stat}>OI {fmtOi(contract.oi.at(-1) ?? 0)}</span>
                  <span className={s.stat}>Vol {fmtOi(contract.volume.at(-1) ?? 0)}</span>
                </button>
              </li>
            );
          })}
          {visible.length === 0 ? <li className={s.none}>No contracts match.</li> : null}
        </ul>

        <footer className={s.foot}>
          <button type="button" className={s.ghost} onClick={() => setPicks([])}>
            Clear
          </button>
          <button type="button" className={s.primary} onClick={() => onApply(picks)}>
            Apply
          </button>
        </footer>
      </div>
    </div>
  );
}
