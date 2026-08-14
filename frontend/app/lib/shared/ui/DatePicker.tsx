import { useEffect, useMemo, useRef, useState } from 'react';
import { isoDateIST } from '$shared/formatting/ist-clock';
import { cx } from './cx';
import IconChevronDown from './icons/IconChevronDown';
import s from './DatePicker.module.css';

/**
 * A month-grid calendar in a popover, replacing the browser's native date input.
 *
 * Values are plain `YYYY-MM-DD` calendar strings and are parsed and formatted
 * *by their parts*, never through the `Date`-then-UTC round trip that shifts a
 * day across the international date line. The month grid, on the other hand, is
 * laid out with `Date.UTC` arithmetic precisely because that is timezone-free —
 * "the 1st of this month" is the same instant everywhere.
 *
 * Monday-first, six rows always (so the popover never changes height), with
 * out-of-month days dimmed, the selection filled, today dotted, and any day past
 * `max` disabled.
 */
interface Props {
  /** Selected day, `YYYY-MM-DD`. */
  value: string;
  /** Latest selectable day, `YYYY-MM-DD`. Days after it are disabled. */
  max?: string | undefined;
  /** Earliest selectable day, `YYYY-MM-DD`. Days before it are disabled. */
  min?: string | undefined;
  onChange: (value: string) => void;
  ariaLabel?: string | undefined;
}

const MONTHS = [
  'January',
  'February',
  'March',
  'April',
  'May',
  'June',
  'July',
  'August',
  'September',
  'October',
  'November',
  'December'
];
const MONTHS_SHORT = MONTHS.map((m) => m.slice(0, 3));
const WEEKDAYS = ['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su'];

interface Ymd {
  y: number;
  m: number; // 0-based
  d: number;
}

function parseYmd(iso: string): Ymd {
  const [y, m, d] = iso.split('-').map(Number);
  return { y: y ?? 1970, m: (m ?? 1) - 1, d: d ?? 1 };
}

function toIso(y: number, m: number, d: number): string {
  return `${y}-${String(m + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
}

export default function DatePicker({ value, max, min, onChange, ariaLabel }: Props) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);

  const selected = parseYmd(value);
  const [viewY, setViewY] = useState(selected.y);
  const [viewM, setViewM] = useState(selected.m);

  // Re-centre the grid on the selected month each time the popover opens, so a
  // value changed while it was closed is what you land on.
  useEffect(() => {
    if (open) {
      setViewY(selected.y);
      setViewM(selected.m);
    }
    // Only when `open` flips — the selected parts are read fresh above.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  useEffect(() => {
    if (!open) return;
    function onDown(event: MouseEvent) {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    }
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') setOpen(false);
    }
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const today = isoDateIST(0);

  const cells = useMemo(() => {
    // Monday-first weekday of the 1st: JS getUTCDay is Sun=0, so shift by 6.
    const firstDow = (new Date(Date.UTC(viewY, viewM, 1)).getUTCDay() + 6) % 7;
    return Array.from({ length: 42 }, (_, i) => {
      const dt = new Date(Date.UTC(viewY, viewM, 1 - firstDow + i));
      const y = dt.getUTCFullYear();
      const m = dt.getUTCMonth();
      const d = dt.getUTCDate();
      return { y, m, d, iso: toIso(y, m, d), inMonth: m === viewM };
    });
  }, [viewY, viewM]);

  function shiftMonth(delta: number) {
    const next = new Date(Date.UTC(viewY, viewM + delta, 1));
    setViewY(next.getUTCFullYear());
    setViewM(next.getUTCMonth());
  }

  // Don't let the header walk past the month that holds `max` — every day beyond
  // it is disabled anyway, so an empty future month is just a dead end.
  const maxYmd = max === undefined ? null : parseYmd(max);
  const nextDisabled =
    maxYmd !== null && (viewY > maxYmd.y || (viewY === maxYmd.y && viewM >= maxYmd.m));

  const label = `${selected.d} ${MONTHS_SHORT[selected.m]} ${selected.y}`;

  return (
    <div className={s.root} ref={root}>
      <button
        type="button"
        className={s.trigger}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label={ariaLabel ?? 'Choose a date'}
        onClick={() => setOpen((o) => !o)}
      >
        <span>{label}</span>
        <span className={s.caret} aria-hidden="true">
          <IconChevronDown />
        </span>
      </button>

      {open ? (
        <div className={s.pop} role="dialog" aria-label="Calendar">
          <div className={s.head}>
            <button
              type="button"
              className={s.nav}
              aria-label="Previous month"
              onClick={() => shiftMonth(-1)}
            >
              ‹
            </button>
            <span className={s.month}>
              {MONTHS[viewM]} {viewY}
            </span>
            <button
              type="button"
              className={s.nav}
              aria-label="Next month"
              disabled={nextDisabled}
              onClick={() => shiftMonth(1)}
            >
              ›
            </button>
          </div>

          <div className={s.weekdays} aria-hidden="true">
            {WEEKDAYS.map((day) => (
              <span key={day} className={s.weekday}>
                {day}
              </span>
            ))}
          </div>

          <div className={s.grid} role="grid">
            {cells.map((cell) => {
              const isSelected = cell.iso === value;
              const isToday = cell.iso === today;
              const disabled =
                (max !== undefined && cell.iso > max) || (min !== undefined && cell.iso < min);
              return (
                <button
                  key={cell.iso}
                  type="button"
                  role="gridcell"
                  aria-selected={isSelected}
                  aria-current={isToday ? 'date' : undefined}
                  disabled={disabled}
                  className={cx(
                    s.day,
                    !cell.inMonth && s.outside,
                    isSelected && s.selected,
                    isToday && s.today
                  )}
                  onClick={() => {
                    onChange(cell.iso);
                    setOpen(false);
                  }}
                >
                  {cell.d}
                </button>
              );
            })}
          </div>
        </div>
      ) : null}
    </div>
  );
}
