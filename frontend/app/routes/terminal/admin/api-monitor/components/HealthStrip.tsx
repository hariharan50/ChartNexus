import { formatAgo, formatMs, formatPercent, providerLabel } from '$contexts/api-monitor/api';
import type { ProviderHealth } from '$contexts/api-monitor/types';
import { cx } from '$shared/ui/cx';
import s from './HealthStrip.module.css';

const STATUS_TEXT: Record<ProviderHealth['status'], string> = {
  healthy: 'Healthy',
  degraded: 'Degraded',
  down: 'Failing',
  idle: 'Idle'
};

/**
 * One card per provider, judged on the last 15 minutes: is it answering, how
 * fast, and when it last failed. Clicking a card filters the page to it.
 */
export default function HealthStrip({
  rows,
  now,
  selected,
  onSelect
}: {
  rows: ProviderHealth[];
  now: number;
  selected: string | null;
  onSelect: (provider: string | null) => void;
}) {
  if (rows.length === 0) return null;
  return (
    <div className={s.strip} role="group" aria-label="Provider health">
      {rows.map((row) => {
        const active = selected === row.provider;
        return (
          <button
            key={row.provider}
            type="button"
            className={cx(s.card, active && s.active)}
            aria-pressed={active}
            onClick={() => onSelect(active ? null : row.provider)}
            title={active ? 'Show every provider' : `Show only ${providerLabel(row.provider)}`}
          >
            <span className={s.top}>
              <span className={s.name}>{providerLabel(row.provider)}</span>
              <span className={cx(s.pill, s[row.status])}>
                <i aria-hidden="true" />
                {STATUS_TEXT[row.status]}
              </span>
            </span>
            <span className={s.metrics}>
              <span>
                <b className="cn-numeric">{row.recent_calls}</b> calls
              </span>
              <span>
                <b className="cn-numeric">{formatMs(row.recent_p95_ms)}</b> p95
              </span>
              <span>
                <b className="cn-numeric">{formatPercent(row.recent_error_rate)}</b> err
              </span>
            </span>
            <span className={s.foot}>
              <span>Last call {formatAgo(row.last_call_ms, now)}</span>
              {row.peak_per_minute !== null ? <span>Peak {row.peak_per_minute}/min</span> : null}
            </span>
            {row.last_error ? (
              <span className={s.error}>
                Last error {row.last_error} · {formatAgo(row.last_error_ms, now)}
              </span>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}
