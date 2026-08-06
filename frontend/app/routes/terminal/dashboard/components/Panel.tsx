import type { ReactNode } from 'react';
import { cx } from '$shared/ui/cx';
import s from './Panel.module.css';

interface Props {
  /** Small leading icon rendered in the header. */
  icon?: ReactNode;
  title?: string | undefined;
  subtitle?: string | undefined;
  /** Right-aligned header content (tabs, badges, actions). */
  actions?: ReactNode;
  /** A coloured left accent bar — used by the AI summary panel. */
  accent?: boolean;
  padded?: boolean;
  children: ReactNode;
}

export default function Panel({
  icon,
  title,
  subtitle,
  actions,
  accent = false,
  padded = true,
  children
}: Props) {
  const hasHeader = Boolean(icon || title || actions);

  return (
    <section className={cx(s.panel, accent && s.accent)}>
      {hasHeader ? (
        <header className={s.panelHead}>
          <div className={s.lead}>
            {icon ? (
              <span className={s.icon} aria-hidden="true">
                {icon}
              </span>
            ) : null}
            {title ? (
              <div className={s.titles}>
                <h2>{title}</h2>
                {subtitle ? <p>{subtitle}</p> : null}
              </div>
            ) : null}
          </div>
          {actions ? <div className={s.actions}>{actions}</div> : null}
        </header>
      ) : null}

      <div className={cx(s.body, padded && s.padded)}>{children}</div>
    </section>
  );
}
