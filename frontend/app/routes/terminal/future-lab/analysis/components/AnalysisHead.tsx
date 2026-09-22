import type { ReactNode } from 'react';
import type { DataSourceName } from '$contexts/broker-connections/types';
import { INDICES, type IndexId } from '$contexts/market-breadth/api';
import DataSourceBadge from '$shared/ui/DataSourceBadge';
import { cx } from '$shared/ui/cx';
import s from '../analysis.module.css';

/**
 * The header furniture the six Analysis pages share.
 *
 * Three small components rather than one configurable block: the pages do not
 * all have an index (the two flow pages have a session count instead), and a
 * single component with four optional slots would be harder to read than these.
 */

interface HeadProps {
  icon: ReactNode;
  title: string;
  /** One line under the title saying what the page is measuring. */
  subtitle: string;
  children?: ReactNode;
}

export function AnalysisHead({ icon, title, subtitle, children }: HeadProps) {
  return (
    <header className={s.header}>
      <div className={s.titleWrap}>
        <h1 className={s.title}>
          <span className={s.titleIco} aria-hidden="true">
            {icon}
          </span>
          {title}
        </h1>
        <p className={s.subtitle}>{subtitle}</p>
      </div>
      <div className={s.headerRight}>{children}</div>
    </header>
  );
}

/**
 * Which index the four index pages are drawn for.
 *
 * A segmented control rather than a dropdown: there are two options and a
 * dropdown would hide one of them behind a click.
 */
export function IndexPicker({
  value,
  onChange
}: {
  value: IndexId;
  onChange: (next: IndexId) => void;
}) {
  return (
    <div className={s.segmented} role="group" aria-label="Index">
      {INDICES.map((entry) => (
        <button
          key={entry.id}
          type="button"
          className={cx(s.segment, entry.id === value && s.segmentOn)}
          aria-pressed={entry.id === value}
          onClick={() => onChange(entry.id)}
        >
          {entry.label}
        </button>
      ))}
    </div>
  );
}

/** How many sessions of history the two flow pages request. */
export function SessionPicker({
  value,
  options,
  onChange
}: {
  value: number;
  options: number[];
  onChange: (next: number) => void;
}) {
  return (
    <div className={s.segmented} role="group" aria-label="Sessions">
      {options.map((count) => (
        <button
          key={count}
          type="button"
          className={cx(s.segment, count === value && s.segmentOn)}
          aria-pressed={count === value}
          onClick={() => onChange(count)}
        >
          {count}d
        </button>
      ))}
    </div>
  );
}

/**
 * Where the numbers came from.
 *
 * Rendered only once a payload has arrived: a badge that reads "Simulated"
 * while the page is still loading is asserting something about data that has
 * not been fetched.
 */
export function SourceBadge({ source }: { source: DataSourceName | undefined }) {
  return source ? <DataSourceBadge source={source} /> : null;
}
