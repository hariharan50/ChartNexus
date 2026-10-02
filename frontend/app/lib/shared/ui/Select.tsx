import { useCallback, useEffect, useId, useRef, useState, type KeyboardEvent } from 'react';
import { cx } from './cx';
import IconCheck from './icons/IconCheck';
import IconChevronDown from './icons/IconChevronDown';
import s from './Select.module.css';

/**
 * The app's dropdown. A listbox, never a `<select>`.
 *
 * The native control hands its popup to the operating system, which draws it in
 * the OS palette — a white sheet with a blue highlight over a dark terminal, in
 * a font and a row height nothing else on the page shares, and in four different
 * shapes across four browsers. Owning the popup also buys what the native
 * control cannot render: a tick on the chosen row, and two aligned secondary
 * columns, so a list of contracts reads down its countdowns instead of trailing
 * them after each date.
 *
 * The keyboard contract is the platform one — Up/Down/Home/End to move, Enter or
 * Space to choose, Escape to dismiss, Tab to move on — so nothing is lost in the
 * trade. Lifted out of the Future Lab expiry picker, which is where this shape
 * was first proven; that picker keeps its own copy only because its rows carry
 * a series index rather than a value.
 */

export interface SelectOption<T extends string = string> {
  value: T;
  label: string;
  /** Right-aligned secondary column, e.g. `26d`. Kept in its own column so a
   *  `6d` and a `61d` end on the same pixel. */
  meta?: string | undefined;
  /** Trailing descriptor, e.g. `Near month`. */
  hint?: string | undefined;
  disabled?: boolean | undefined;
}

interface Props<T extends string> {
  value: T;
  options: readonly SelectOption<T>[];
  onChange: (value: T) => void;
  /** Names the control for a screen reader; required, as there is no `<label>`. */
  ariaLabel: string;
  /** Shown on the trigger when `value` matches no option. */
  placeholder?: string | undefined;
  disabled?: boolean | undefined;
  /** `sm` matches a toolbar's compact controls; `md` is the default row height. */
  size?: 'sm' | 'md' | undefined;
  /** Opens the list right-aligned to the trigger, for controls near the edge. */
  align?: 'left' | 'right' | undefined;
  className?: string | undefined;
}

export default function Select<T extends string>({
  value,
  options,
  onChange,
  ariaLabel,
  placeholder = 'Select',
  disabled = false,
  size = 'md',
  align = 'left',
  className
}: Props<T>) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const list = useRef<HTMLUListElement>(null);
  const listId = useId();

  const close = useCallback((restoreFocus: boolean) => {
    setOpen(false);
    if (restoreFocus) trigger.current?.focus();
  }, []);

  // Pointer down rather than click: a click that starts inside the popup and
  // ends outside it is a drag across a row, not a dismissal.
  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: PointerEvent) {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener('pointerdown', onPointerDown);
    return () => document.removeEventListener('pointerdown', onPointerDown);
  }, [open]);

  // Focus lands on the selected row, so a keyboard user starts where a mouse
  // user is already looking.
  useEffect(() => {
    if (!open) return;
    const active = list.current?.querySelector<HTMLElement>('[aria-selected="true"]');
    (active ?? list.current?.querySelector<HTMLElement>('[role="option"]'))?.focus();
  }, [open]);

  // An options list can change under a control — an expiry settles, a symbol
  // leaves the catalogue — and a popup left open over rows that have shifted
  // would choose the wrong one. Keyed on the rows themselves, not on the array:
  // callers build `options` inline, so a new array arrives on every render, and
  // a page that polls would otherwise slam its own popup shut mid-choice.
  const signature = JSON.stringify(options.map((option) => [option.value, option.label]));
  useEffect(() => setOpen(false), [signature]);

  function choose(option: SelectOption<T>): void {
    if (option.disabled) return;
    onChange(option.value);
    close(true);
  }

  function onListKeyDown(event: KeyboardEvent<HTMLUListElement>): void {
    const items = Array.from(list.current?.querySelectorAll<HTMLElement>('[role="option"]') ?? []);
    const at = items.indexOf(document.activeElement as HTMLElement);

    switch (event.key) {
      case 'Escape':
        event.stopPropagation();
        close(true);
        return;
      case 'Tab':
        // Tab moves on rather than cycling inside: this is a menu, not a
        // dialog, and trapping focus in it would be a trap.
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

  const selected = options.find((option) => option.value === value);
  const empty = options.length === 0;

  return (
    <div className={cx(s.select, className)} ref={root}>
      <button
        ref={trigger}
        type="button"
        className={cx(s.trigger, size === 'sm' && s.triggerSm, open && s.triggerOpen)}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={ariaLabel}
        aria-controls={open ? listId : undefined}
        disabled={disabled || empty}
        onClick={() => setOpen((was) => !was)}
        onKeyDown={(event) => {
          if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
            event.preventDefault();
            setOpen(true);
          }
        }}
      >
        <span className={s.triggerLabel}>{selected?.label ?? placeholder}</span>
        <span className={cx(s.caret, open && s.caretOpen)} aria-hidden="true">
          <IconChevronDown />
        </span>
      </button>

      {open ? (
        <ul
          ref={list}
          id={listId}
          className={cx(s.list, align === 'right' && s.listRight)}
          role="listbox"
          aria-label={ariaLabel}
          onKeyDown={onListKeyDown}
        >
          {options.map((option) => {
            const isSelected = option.value === value;
            return (
              <li
                key={option.value}
                role="option"
                tabIndex={-1}
                aria-selected={isSelected}
                aria-disabled={option.disabled || undefined}
                className={cx(s.option, isSelected && s.optionOn, option.disabled && s.optionOff)}
                onClick={() => choose(option)}
                onKeyDown={(event) => {
                  if (event.key !== 'Enter' && event.key !== ' ') return;
                  event.preventDefault();
                  choose(option);
                }}
              >
                <span className={s.tick} aria-hidden="true">
                  {isSelected ? <IconCheck /> : null}
                </span>
                <span className={s.optionLabel}>{option.label}</span>
                <span className={s.optionMeta}>{option.meta ?? ''}</span>
                <span className={s.optionHint}>{option.hint ?? ''}</span>
              </li>
            );
          })}
        </ul>
      ) : null}
    </div>
  );
}
