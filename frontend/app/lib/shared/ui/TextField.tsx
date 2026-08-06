import { useId, type ComponentPropsWithoutRef, type ReactNode } from 'react';
import { cx } from './cx';
import s from './TextField.module.css';

interface Props extends Omit<
  ComponentPropsWithoutRef<'input'>,
  'value' | 'onChange' | 'className'
> {
  label: string;
  value: string;
  /**
   * Applied to the field wrapper, not the `<input>`.
   *
   * Svelte let a parent reach in with `form :global(.field)`; CSS Modules hashes
   * that class, so layout the parent owns — a width, a grid placement — comes in
   * through here instead.
   */
  className?: string | undefined;
  /**
   * Svelte bound this with `bind:value`. React has no two-way binding, so the
   * field is controlled: the owner holds the value and gets told when to change
   * it.
   */
  onValueChange?: ((value: string) => void) | undefined;
  error?: string | undefined;
  /** Leading glyph, rendered decoratively inside the field. */
  icon?: ReactNode;
  /**
   * Leading content that carries meaning — a country code, a currency
   * symbol. Unlike `icon` it is not `aria-hidden`, because a screen reader
   * has to announce it to make sense of what is typed.
   */
  leading?: ReactNode;
  /** Trailing control, e.g. a password reveal toggle. */
  trailing?: ReactNode;
}

export default function TextField({
  label,
  value,
  onValueChange,
  error,
  icon,
  leading,
  trailing,
  id,
  onInput,
  className,
  ...rest
}: Props) {
  // useId is stable across re-renders and identical between the server and
  // client renders, so hydration does not swap the label's `for` target.
  const uid = useId();
  const fieldId = id ?? uid;
  const errorId = `${fieldId}-error`;

  return (
    <div className={cx(s.field, className)}>
      <label htmlFor={fieldId}>{label}</label>

      <div className={cx(s.shell, !!error && s.invalid)}>
        {icon ? (
          <span className={s.icon} aria-hidden="true">
            {icon}
          </span>
        ) : null}

        {leading ? <span className={s.leading}>{leading}</span> : null}

        <input
          id={fieldId}
          value={value}
          onChange={(event) => onValueChange?.(event.currentTarget.value)}
          onInput={onInput}
          aria-invalid={error ? 'true' : undefined}
          aria-describedby={error ? errorId : undefined}
          {...rest}
        />

        {trailing ? <span className={s.trailing}>{trailing}</span> : null}
      </div>

      {error ? (
        <p className={s.error} id={errorId}>
          {error}
        </p>
      ) : null}
    </div>
  );
}
