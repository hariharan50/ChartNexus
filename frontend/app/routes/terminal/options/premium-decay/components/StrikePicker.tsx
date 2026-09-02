import { useEffect, useRef, useState } from 'react';
import { cx } from '$shared/ui/cx';
import s from '../route.module.css';

/**
 * Pick strikes off the session axis for the Fixed and Custom windows.
 *
 * `single` picks one anchor strike (Fixed Strike ± range centres on it);
 * `multi` hand-picks the set the Custom window totals. A modal rather than an
 * inline list because the axis runs to ~50 strikes — more than the sidebar can
 * hold, and choosing among them is a task, not a glance.
 *
 * Focus is trapped and restored and Escape closes: this sits over a live,
 * polling page, so leaving focus behind would let a keyboard user tab into a
 * chart they cannot see.
 */
interface Props {
  strikes: number[];
  atm: number | null;
  selectMode: 'single' | 'multi';
  /** The current selection: one strike (single) or many (multi). */
  selected: number[];
  title: string;
  hint: string;
  onApply: (strikes: number[]) => void;
  onClose: () => void;
}

export default function StrikePicker({
  strikes,
  atm,
  selectMode,
  selected,
  title,
  hint,
  onApply,
  onClose
}: Props) {
  const [picks, setPicks] = useState<number[]>(selected);
  const dialog = useRef<HTMLDivElement>(null);
  const opener = useRef<Element | null>(null);

  useEffect(() => {
    opener.current = document.activeElement;
    dialog.current?.querySelector<HTMLElement>('button')?.focus();
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

  function toggle(strike: number) {
    if (selectMode === 'single') {
      setPicks([strike]);
      return;
    }
    setPicks((current) =>
      current.includes(strike) ? current.filter((value) => value !== strike) : [...current, strike]
    );
  }

  return (
    <div className={s.backdrop} onPointerDown={onClose}>
      <div
        className={s.dialog}
        ref={dialog}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onPointerDown={(event) => event.stopPropagation()}
      >
        <header className={s.dialogHead}>
          <h2 className={s.dialogTitle}>{title}</h2>
          <button type="button" className={s.close} onClick={onClose} aria-label="Close">
            ×
          </button>
        </header>

        <p className={s.dialogHint}>{hint}</p>

        <ul className={s.strikeList}>
          {strikes.map((strike) => {
            const on = picks.includes(strike);
            return (
              <li key={strike}>
                <button
                  type="button"
                  className={cx(s.strikeOpt, on && s.on, strike === atm && s.atm)}
                  onClick={() => toggle(strike)}
                  aria-pressed={on}
                >
                  {strike}
                </button>
              </li>
            );
          })}
          {strikes.length === 0 ? <li>No strikes on this session yet.</li> : null}
        </ul>

        <footer className={s.dialogFoot}>
          {selectMode === 'multi' ? (
            <button type="button" className={s.ghost} onClick={() => setPicks([])}>
              Clear
            </button>
          ) : null}
          <button
            type="button"
            className={s.primary}
            onClick={() => onApply(picks)}
            disabled={picks.length === 0}
          >
            Apply
          </button>
        </footer>
      </div>
    </div>
  );
}
