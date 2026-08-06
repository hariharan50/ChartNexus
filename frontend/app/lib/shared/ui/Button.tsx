import type { ComponentPropsWithoutRef, ReactNode } from 'react';
import { cx } from './cx';
import s from './Button.module.css';

type Variant = 'primary' | 'secondary' | 'ghost';

interface Props extends ComponentPropsWithoutRef<'button'> {
  variant?: Variant | undefined;
  loading?: boolean | undefined;
  full?: boolean | undefined;
  children: ReactNode;
}

export default function Button({
  variant = 'primary',
  loading = false,
  full = false,
  disabled = false,
  type = 'button',
  children,
  ...rest
}: Props) {
  return (
    <button
      type={type}
      className={cx(s.btn, s[variant], full && s.full)}
      disabled={disabled || loading}
      aria-busy={loading}
      {...rest}
    >
      {loading ? <span className={s.spinner} aria-hidden="true" /> : null}
      {children}
    </button>
  );
}
