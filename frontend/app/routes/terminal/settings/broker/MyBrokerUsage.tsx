import { useQuery } from '@tanstack/react-query';
import {
  formatCount,
  formatMs,
  formatPercent,
  getMyUsage,
  providerLabel
} from '$contexts/api-monitor/api';
import UsageChart from '../../admin/api-monitor/components/UsageChart';
import s from './MyBrokerUsage.module.css';

/**
 * "My broker usage" — calls made with this user's own Kite / FYERS app over
 * the last 24 hours, and how much of today's quota they spent.
 *
 * The server filters to the caller's own app before anything is summed, so
 * nothing here can describe another user. Market-wide jobs that happen to run
 * on this connection are included, because they spend its quota.
 */
export default function MyBrokerUsage() {
  const usage = useQuery({
    queryKey: ['api-monitor', 'mine'],
    queryFn: () => getMyUsage('24h'),
    refetchInterval: 60_000
  });

  const report = usage.data;
  return (
    <article className={s.card} aria-labelledby="my-broker-usage">
      <div className={s.head}>
        <h3 id="my-broker-usage">My broker usage</h3>
        <span className={s.window}>last 24 hours</span>
      </div>
      {usage.isError ? (
        <p className={s.hint}>Usage is unavailable right now.</p>
      ) : !report ? (
        <p className={s.hint}>Loading…</p>
      ) : report.totals.calls === 0 && report.quotas.length === 0 ? (
        <p className={s.hint}>
          No broker calls recorded yet. Once your broker is connected and you open a chart, its
          requests show up here.
        </p>
      ) : (
        <>
          <dl className={s.stats}>
            <div>
              <dt>Requests</dt>
              <dd className="cn-numeric">{formatCount(report.totals.calls)}</dd>
            </div>
            <div>
              <dt>Errors</dt>
              <dd className="cn-numeric">{formatPercent(report.totals.error_rate)}</dd>
            </div>
            <div>
              <dt>p95 latency</dt>
              <dd className="cn-numeric">{formatMs(report.totals.p95_ms)}</dd>
            </div>
            <div>
              <dt>Avg latency</dt>
              <dd className="cn-numeric">{formatMs(report.totals.avg_ms)}</dd>
            </div>
          </dl>
          <UsageChart
            series={report.series}
            stepSeconds={report.step_seconds}
            height={70}
            compact
          />
          {report.quotas.map((quota) => (
            <p className={s.hint} key={`${quota.broker}${quota.app_label}`}>
              {providerLabel(quota.broker)} quota today:{' '}
              <span className="cn-numeric">
                {formatCount(quota.used_today)} of {formatCount(quota.daily_limit)}
              </span>{' '}
              ({quota.window})
            </p>
          ))}
        </>
      )}
    </article>
  );
}
