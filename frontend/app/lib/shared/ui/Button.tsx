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
      className={cx(s.btn, s[variant], full && s.full, loading && s.busy)}
      disabled={disabled || loading}
      aria-busy={loading}
      {...rest}
    >
      {/* The label stays in the flow (only hidden) while the spinner overlays
          it, so the button keeps its exact width and nothing beside it
          reflows when an async action starts or ends. */}
      <span className={cx(s.label, loading && s.labelHidden)}>{children}</span>
      {loading ? <span className={s.spinner} aria-hidden="true" /> : null}
    </button>
  );
}
