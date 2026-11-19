import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import {
  delta,
  formatAgo,
  formatCount,
  formatMs,
  formatPercent,
  formatRate,
  getAdminRoster,
  getPlatformUsage,
  providerLabel,
  toCsv,
  type Delta
} from '$contexts/api-monitor/api';
import type {
  CallStats,
  EndpointRow,
  RecentCall,
  UsageFilters,
  UsageRange,
  UsageReport
} from '$contexts/api-monitor/types';
import { ApiError } from '$shared/api/errors';
import { cx } from '$shared/ui/cx';
import HealthStrip from './components/HealthStrip';
import LatencyHistogram from './components/LatencyHistogram';
import UsageChart from './components/UsageChart';
import s from './api-monitor.module.css';
import type { Route } from './+types/route';

export const meta: Route.MetaFunction = () => [{ title: 'API Monitor · Admin · ChartNexus' }];

const RANGES: readonly UsageRange[] = ['1h', '6h', '24h', '7d'];
const REFRESH_MS = 15_000;
const SLOW_MS = 1000;
const NO_FILTERS: UsageFilters = { provider: null, origin: null, endpoint: null };

type SortKey = 'calls' | 'error_rate' | 'avg_ms' | 'p95_ms' | 'p99_ms';
type RecentView = 'all' | 'errors' | 'slow';

const SORTS: readonly { key: SortKey; label: string }[] = [
  { key: 'calls', label: 'Calls' },
  { key: 'error_rate', label: 'Errors' },
  { key: 'avg_ms', label: 'Avg' },
  { key: 'p95_ms', label: 'p95' },
  { key: 'p99_ms', label: 'p99' }
];

const RECENT_VIEWS: readonly { key: RecentView; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'errors', label: 'Errors' },
  { key: 'slow', label: `Slow ≥ ${SLOW_MS / 1000} s` }
];

const ERROR_TEXT: Record<string, string> = {
  timeout: 'Timed out',
  connect: 'Could not connect',
  network: 'Network error',
  http_4xx: 'Rejected (4xx)',
  http_429: 'Rate limited (429)',
  http_5xx: 'Server error (5xx)'
};

/**
 * Admin → API Monitor: every outbound call the platform makes.
 *
 * Everything on the page is one server report. Filtering by provider, caller
 * or endpoint asks the server for the same report narrowed down, so a
 * drill-down into one endpoint shows that endpoint's own traffic chart,
 * latency spread, callers and errors, not a client-side slice of the totals.
 *
 * The server decides who may see this (it re-reads the admin role on every
 * request); the page only renders what it is given.
 */
export default function ApiMonitor() {
  const [range, setRange] = useState<UsageRange>('1h');
  const [filters, setFilters] = useState<UsageFilters>(NO_FILTERS);
  const [paused, setPaused] = useState(false);
  const [sort, setSort] = useState<SortKey>('calls');
  const [search, setSearch] = useState('');
  const [recentView, setRecentView] = useState<RecentView>('all');

  const usage = useQuery({
    queryKey: ['admin', 'api-monitor', range, filters],
    queryFn: () => getPlatformUsage(range, filters),
    refetchInterval: paused ? false : REFRESH_MS,
    placeholderData: keepPreviousData,
    retry: (count, error) => !(error instanceof ApiError && error.status === 403) && count < 2
  });
  const roster = useQuery({
    queryKey: ['admin', 'admins'],
    queryFn: getAdminRoster,
    enabled: usage.isSuccess
  });

  const report = usage.data;

  const endpoints = useMemo(() => {
    const needle = search.trim().toLowerCase();
    const rows = (report?.endpoints ?? []).filter(
      (row) =>
        !needle ||
        row.endpoint.toLowerCase().includes(needle) ||
        providerLabel(row.provider).toLowerCase().includes(needle)
    );
    return [...rows].sort((a, b) => (b[sort] ?? -1) - (a[sort] ?? -1));
  }, [report, sort, search]);

  const recent = useMemo(() => {
    const rows = report?.recent ?? [];
    if (recentView === 'errors') return rows.filter((call) => call.error);
    if (recentView === 'slow') return rows.filter((call) => call.elapsed_ms >= SLOW_MS);
    return rows;
  }, [report, recentView]);

  if (usage.error instanceof ApiError && usage.error.status === 403) {
    return (
      <section className={s.page}>
        <div className={s.denied} role="alert">
          <h1>Admins only</h1>
          <p>Your account does not have access to this page.</p>
        </div>
      </section>
    );
  }

  const set = (patch: Partial<UsageFilters>) => setFilters((current) => ({ ...current, ...patch }));
  const filtered = Boolean(filters.provider || filters.origin || filters.endpoint);
  const now = report?.generated_at_ms ?? 0;

  return (
    <section className={s.page}>
      <header className={s.head}>
        <div>
          <p className={s.eyebrow}>Admin</p>
          <h1 className={s.title}>API Latency Monitor</h1>
          <p className={s.sub}>
            Every outbound call ChartNexus makes — brokers, exchanges and alert channels — with its
            latency, errors and who asked for it.
          </p>
        </div>
        <div className={s.controls}>
          <span className={cx(s.live, paused && s.livePaused)} aria-live="polite">
            <i aria-hidden="true" />
            {liveText(paused, usage.isFetching, report)}
          </span>
          <button type="button" className={s.ghost} onClick={() => setPaused((value) => !value)}>
            {paused ? 'Resume' : 'Pause'}
          </button>
          <button
            type="button"
            className={s.ghost}
            onClick={() => void usage.refetch()}
            disabled={usage.isFetching}
          >
            Refresh
          </button>
          <Segmented
            label="Time range"
            options={RANGES.map((value) => ({ key: value, label: value }))}
            value={range}
            onChange={setRange}
          />
        </div>
      </header>

      <div className={s.filters}>
        <label className={s.select}>
          <span>Provider</span>
          <select
            value={filters.provider ?? ''}
            onChange={(event) => set({ provider: event.target.value || null, endpoint: null })}
          >
            <option value="">All providers</option>
            {(report?.options.providers ?? []).map((provider) => (
              <option key={provider} value={provider}>
                {providerLabel(provider)}
              </option>
            ))}
          </select>
        </label>
        <label className={s.select}>
          <span>Caller</span>
          <select
            value={filters.origin ?? ''}
            onChange={(event) => set({ origin: event.target.value || null })}
          >
            <option value="">All callers</option>
            {(report?.options.origins ?? []).map((origin) => (
              <option key={origin} value={origin}>
                {origin}
              </option>
            ))}
          </select>
        </label>
        {filters.endpoint ? (
          <span className={s.chip}>
            Endpoint <code>{filters.endpoint}</code>
            <button
              type="button"
              aria-label="Clear endpoint filter"
              onClick={() => set({ endpoint: null })}
            >
              ×
            </button>
          </span>
        ) : null}
        {filtered ? (
          <button type="button" className={s.ghost} onClick={() => setFilters(NO_FILTERS)}>
            Clear filters
          </button>
        ) : null}
      </div>

      {usage.isError && !report ? (
        <div className={s.banner} role="alert">
          Could not load the monitor. It will retry automatically.
        </div>
      ) : null}

      {!report ? (
        <p className={s.hint}>Loading…</p>
      ) : (
        <>
          {filters.endpoint ? (
            <div className={s.drill}>
              <div>
                <p className={s.eyebrow}>Endpoint detail</p>
                <h2 className={s.drillTitle}>
                  {providerLabel(filters.provider ?? '')} <code>{filters.endpoint}</code>
                </h2>
              </div>
              <button type="button" className={s.ghost} onClick={() => set({ endpoint: null })}>
                ← All endpoints
              </button>
            </div>
          ) : (
            <HealthStrip
              rows={report.health}
              now={now}
              selected={filters.provider}
              onSelect={(provider) => set({ provider, endpoint: null })}
            />
          )}

          <Kpis report={report} />

          <div className={s.columns2}>
            <article className={s.card}>
              <div className={s.cardHead}>
                <h2>Traffic</h2>
                <span className={s.hintInline}>
                  {report.step_seconds >= 3600
                    ? 'per hour'
                    : `per ${Math.round(report.step_seconds / 60)} min`}
                </span>
              </div>
              <UsageChart series={report.series} stepSeconds={report.step_seconds} />
            </article>
            <article className={s.card}>
              <div className={s.cardHead}>
                <h2>Latency distribution</h2>
                <span className={s.hintInline}>
                  p50 {formatMs(report.totals.p50_ms)} · p90 {formatMs(report.totals.p90_ms)} · p99{' '}
                  {formatMs(report.totals.p99_ms)}
                </span>
              </div>
              <LatencyHistogram buckets={report.totals.histogram} />
            </article>
          </div>

          <div className={s.columns3}>
            <article className={s.card}>
              <h2>Errors</h2>
              <ErrorBreakdown stats={report.totals} recent={report.recent} now={now} />
            </article>
            <article className={s.card}>
              <h2>Who is calling</h2>
              <p className={s.hint}>
                Background jobs by name, page requests by path. Click a row to filter.
              </p>
              <StatsTable
                rows={report.origins.map((row) => ({
                  key: row.origin,
                  label: row.origin,
                  stats: row
                }))}
                activeKey={filters.origin}
                onPick={(origin) => set({ origin: filters.origin === origin ? null : origin })}
              />
            </article>
            <article className={s.card}>
              <h2>Broker connections</h2>
              <p className={s.hint}>Calls per broker app, by masked app id.</p>
              <StatsTable
                rows={report.apps.map((row) => ({
                  key: row.app_label,
                  label: `${row.broker ? `${providerLabel(row.broker)} ` : ''}${row.app_label}`,
                  stats: row
                }))}
              />
            </article>
          </div>

          {filters.endpoint ? null : (
            <article className={s.card}>
              <div className={s.cardHead}>
                <h2>Endpoints</h2>
                <div className={s.tableTools}>
                  <input
                    className={s.search}
                    type="search"
                    placeholder="Search endpoints…"
                    value={search}
                    onChange={(event) => setSearch(event.target.value)}
                    aria-label="Search endpoints"
                  />
                  <Segmented
                    label="Sort endpoints by"
                    options={SORTS}
                    value={sort}
                    onChange={setSort}
                  />
                  <button
                    type="button"
                    className={s.ghost}
                    onClick={() => downloadEndpoints(report, endpoints)}
                    disabled={endpoints.length === 0}
                  >
                    Export CSV
                  </button>
                </div>
              </div>
              <EndpointTable
                rows={endpoints}
                total={report.totals.calls}
                searching={Boolean(search)}
                onOpen={(row) => set({ provider: row.provider, endpoint: row.endpoint })}
              />
              <p className={s.hint}>
                Click a row for its detail. Percentiles are estimated from latency buckets; ids in
                paths show as <code>{'{id}'}</code>; query strings and credentials are never
                recorded.
              </p>
            </article>
          )}

          <div className={s.columns2}>
            <article className={s.card}>
              <h2>Broker quota today</h2>
              <Quotas report={report} />
            </article>
            <article className={s.card}>
              <h2>Admins</h2>
              {roster.data ? (
                <>
                  <p className={s.hint}>
                    {roster.data.admins.length} of {roster.data.max_admins} admin slots used. Admins
                    are granted and revoked only with <code>chartnexus-admin</code> on the server.
                  </p>
                  <ul className={s.admins}>
                    {roster.data.admins.map((admin) => (
                      <li key={admin.email}>
                        <span>{admin.email}</span>
                        <span className={s.hintInline}>since {admin.since}</span>
                      </li>
                    ))}
                  </ul>
                  {roster.data.audit.length ? (
                    <details className={s.audit}>
                      <summary>Recent admin changes ({roster.data.audit.length})</summary>
                      <ul>
                        {roster.data.audit.map((entry, index) => (
                          <li key={index}>
                            <span className="cn-numeric">
                              {entry.at.slice(0, 16).replace('T', ' ')}
                            </span>{' '}
                            {entry.action.replace('admin.', '')} {entry.email}{' '}
                            <span className={s.hintInline}>by {entry.actor}</span>
                          </li>
                        ))}
                      </ul>
                    </details>
                  ) : null}
                </>
              ) : (
                <p className={s.hint}>Loading…</p>
              )}
            </article>
          </div>

          <article className={s.card}>
            <div className={s.cardHead}>
              <h2>Recent calls</h2>
              <Segmented
                label="Show calls"
                options={RECENT_VIEWS}
                value={recentView}
                onChange={setRecentView}
              />
            </div>
            <RecentTable rows={recent} />
          </article>
        </>
      )}
    </section>
  );
}

function liveText(paused: boolean, fetching: boolean, report: UsageReport | undefined): string {
  if (paused) return 'Paused';
  if (fetching) return 'Updating…';
  return report ? `Live · ${formatClock(report.generated_at_ms)}` : 'Live';
}

function Segmented<K extends string>({
  label,
  options,
  value,
  onChange
}: {
  label: string;
  options: readonly { key: K; label: string }[];
  value: K;
  onChange: (key: K) => void;
}) {
  return (
    <div className={s.segmented} role="group" aria-label={label}>
      {options.map((option) => (
        <button
          key={option.key}
          type="button"
          className={cx(s.segment, option.key === value && s.segmentOn)}
          aria-pressed={option.key === value}
          onClick={() => onChange(option.key)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

function Kpis({ report }: { report: UsageReport }) {
  const { totals, previous } = report;
  return (
    <div className={s.kpis}>
      <Kpi
        label="Requests"
        value={formatCount(totals.calls)}
        change={delta(totals.calls, previous?.calls ?? null)}
      />
      <Kpi
        label="Calls / min now"
        value={formatRate(report.calls_per_minute_now)}
        note={report.range === '7d' ? 'last hour' : 'last 5 min'}
      />
      <Kpi
        label="Peak / min"
        value={report.peak_per_minute === null ? '—' : formatCount(report.peak_per_minute)}
        note={report.peak_per_minute === null ? 'needs 24h or less' : 'busiest minute'}
      />
      <Kpi
        label="Error rate"
        value={formatPercent(totals.error_rate)}
        tone={totals.error_rate > 0.05 ? 'bad' : undefined}
        note={`${formatCount(totals.errors)} failed`}
        change={delta(totals.error_rate, previous?.error_rate ?? null, {
          higherIsWorse: true,
          points: true
        })}
      />
      <Kpi
        label="p95 latency"
        value={formatMs(totals.p95_ms)}
        tone={slow(totals.p95_ms) ? 'bad' : undefined}
        note={`avg ${formatMs(totals.avg_ms)}`}
        change={delta(totals.p95_ms, previous?.p95_ms ?? null, { higherIsWorse: true })}
      />
      <Kpi label="p99 latency" value={formatMs(totals.p99_ms)} note="approx." />
    </div>
  );
}

function Kpi({
  label,
  value,
  note,
  tone,
  change
}: {
  label: string;
  value: string;
  note?: string | undefined;
  tone?: 'bad' | undefined;
  change?: Delta | null | undefined;
}) {
  return (
    <div className={s.kpi}>
      <span className={s.kpiLabel}>{label}</span>
      <span className={cx(s.kpiValue, 'cn-numeric', tone === 'bad' && s.bad)}>{value}</span>
      <span className={s.kpiNote}>
        {change ? (
          <span
            className={cx(s.delta, s[`delta_${change.tone}`])}
            title="Compared with the previous period of the same length"
          >
            {change.text}
          </span>
        ) : null}
        {note ? <span>{note}</span> : null}
      </span>
    </div>
  );
}

function ErrorBreakdown({
  stats,
  recent,
  now
}: {
  stats: CallStats;
  recent: RecentCall[];
  now: number;
}) {
  const classes = Object.entries(stats.errors_by_class).sort((a, b) => b[1] - a[1]);
  const latest = recent.filter((call) => call.error).slice(0, 6);
  if (classes.length === 0) {
    return <p className={s.ok}>No failed calls in this range.</p>;
  }
  return (
    <>
      <ul className={s.errorList}>
        {classes.map(([name, count]) => (
          <li key={name}>
            <span>{ERROR_TEXT[name] ?? name}</span>
            <span className={cx(s.bad, 'cn-numeric')}>{formatCount(count)}</span>
          </li>
        ))}
      </ul>
      {latest.length ? (
        <>
          <p className={s.hint}>Latest failures</p>
          <ul className={s.failures}>
            {latest.map((call, index) => (
              <li key={`${call.at_ms}-${index}`}>
                <span className={s.mono}>
                  {providerLabel(call.provider)} {call.endpoint}
                </span>
                <span className={s.hintInline}>
                  {ERROR_TEXT[call.error ?? ''] ?? call.error} · {formatAgo(call.at_ms, now)}
                </span>
              </li>
            ))}
          </ul>
        </>
      ) : null}
    </>
  );
}

function Quotas({ report }: { report: UsageReport }) {
  if (report.quotas.length === 0) {
    return <p className={s.hint}>No broker quota has been used today.</p>;
  }
  return (
    <ul className={s.quotas}>
      {report.quotas.map((quota) => {
        const share = quota.daily_limit ? quota.used_today / quota.daily_limit : 0;
        return (
          <li key={`${quota.broker}${quota.app_label}`}>
            <div className={s.quotaHead}>
              <span>
                {providerLabel(quota.broker)} <span className={s.mono}>{quota.app_label}</span>
              </span>
              <span className="cn-numeric">
                {formatCount(quota.used_today)} / {formatCount(quota.daily_limit)} ·{' '}
                {formatPercent(share)}
              </span>
            </div>
            <div className={s.meter} aria-hidden="true">
              <span
                className={cx(s.meterFill, share > 0.8 && s.meterHot)}
                style={{ width: `${Math.min(100, share * 100)}%` }}
              />
            </div>
            <p className={s.hint}>Window: {quota.window}</p>
          </li>
        );
      })}
    </ul>
  );
}

function EndpointTable({
  rows,
  total,
  searching,
  onOpen
}: {
  rows: EndpointRow[];
  total: number;
  searching: boolean;
  onOpen: (row: EndpointRow) => void;
}) {
  return (
    <div className={s.scroll}>
      <table className={s.table}>
        <thead>
          <tr>
            <th>Provider</th>
            <th>Endpoint</th>
            <th className={s.num}>Calls</th>
            <th className={s.num}>Share</th>
            <th className={s.num}>Errors</th>
            <th className={s.num}>Avg</th>
            <th className={s.num}>p50</th>
            <th className={s.num}>p95</th>
            <th className={s.num}>p99</th>
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td colSpan={9} className={s.none}>
                {searching ? 'No endpoint matches that search.' : 'No calls in this range.'}
              </td>
            </tr>
          ) : (
            rows.map((row) => (
              <tr
                key={`${row.provider}${row.endpoint}`}
                className={s.clickable}
                tabIndex={0}
                onClick={() => onOpen(row)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    onOpen(row);
                  }
                }}
                title="Open endpoint detail"
              >
                <td>{providerLabel(row.provider)}</td>
                <td className={s.mono}>{row.endpoint}</td>
                <td className={cx(s.num, 'cn-numeric')}>{formatCount(row.calls)}</td>
                <td className={cx(s.num, 'cn-numeric')}>
                  <ShareBar value={row.calls / Math.max(1, total)} />
                </td>
                <td
                  className={cx(s.num, 'cn-numeric', row.errors > 0 && s.bad)}
                  title={errorTitle(row)}
                >
                  {row.errors ? formatPercent(row.error_rate) : '—'}
                </td>
                <td className={cx(s.num, 'cn-numeric')}>{formatMs(row.avg_ms)}</td>
                <td className={cx(s.num, 'cn-numeric')}>{formatMs(row.p50_ms)}</td>
                <td className={cx(s.num, 'cn-numeric', slow(row.p95_ms) && s.warn)}>
                  {formatMs(row.p95_ms)}
                </td>
                <td className={cx(s.num, 'cn-numeric', slow(row.p99_ms) && s.warn)}>
                  {formatMs(row.p99_ms)}
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

function RecentTable({ rows }: { rows: RecentCall[] }) {
  return (
    <div className={cx(s.scroll, s.recent)}>
      <table className={s.table}>
        <thead>
          <tr>
            <th>Time</th>
            <th>Provider</th>
            <th>Endpoint</th>
            <th>Caller</th>
            <th className={s.num}>Status</th>
            <th className={s.num}>Latency</th>
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td colSpan={6} className={s.none}>
                Nothing to show.
              </td>
            </tr>
          ) : (
            rows.map((call, index) => (
              <tr key={`${call.at_ms}-${index}`}>
                <td className="cn-numeric">{formatClock(call.at_ms)}</td>
                <td>{providerLabel(call.provider)}</td>
                <td className={s.mono}>
                  {call.method} {call.endpoint}
                </td>
                <td className={s.mono}>{call.origin}</td>
                <td className={cx(s.num, call.error !== null && s.bad)}>
                  {call.error ? (ERROR_TEXT[call.error] ?? call.error) : (call.status ?? '—')}
                </td>
                <td className={cx(s.num, 'cn-numeric', call.elapsed_ms >= SLOW_MS && s.warn)}>
                  {formatMs(call.elapsed_ms)}
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

function StatsTable({
  rows,
  activeKey,
  onPick
}: {
  rows: { key: string; label: string; stats: CallStats }[];
  activeKey?: string | null;
  onPick?: (key: string) => void;
}) {
  if (rows.length === 0) return <p className={s.hint}>No calls in this range.</p>;
  return (
    <div className={s.scroll}>
      <table className={s.table}>
        <thead>
          <tr>
            <th>Name</th>
            <th className={s.num}>Calls</th>
            <th className={s.num}>Errors</th>
            <th className={s.num}>p95</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={row.key}
              className={cx(onPick && s.clickable, activeKey === row.key && s.selectedRow)}
              onClick={onPick ? () => onPick(row.key) : undefined}
            >
              <td className={s.mono}>{row.label}</td>
              <td className={cx(s.num, 'cn-numeric')}>{formatCount(row.stats.calls)}</td>
              <td className={cx(s.num, 'cn-numeric', row.stats.errors > 0 && s.bad)}>
                {row.stats.errors ? formatPercent(row.stats.error_rate) : '—'}
              </td>
              <td className={cx(s.num, 'cn-numeric', slow(row.stats.p95_ms) && s.warn)}>
                {formatMs(row.stats.p95_ms)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ShareBar({ value }: { value: number }) {
  return (
    <span className={s.share}>
      <span className={s.shareTrack} aria-hidden="true">
        <span className={s.shareFill} style={{ width: `${Math.min(100, value * 100)}%` }} />
      </span>
      {formatPercent(value)}
    </span>
  );
}

function slow(ms: number | null): boolean {
  return ms !== null && ms >= SLOW_MS;
}

function errorTitle(row: CallStats): string {
  return Object.entries(row.errors_by_class)
    .map(([name, count]) => `${ERROR_TEXT[name] ?? name}: ${count}`)
    .join(', ');
}

function formatClock(atMs: number): string {
  return new Date(atMs).toLocaleTimeString('en-IN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false
  });
}

function downloadEndpoints(report: UsageReport, rows: EndpointRow[]): void {
  const csv = toCsv(
    rows.map((row) => ({
      provider: row.provider,
      endpoint: row.endpoint,
      calls: row.calls,
      errors: row.errors,
      error_rate: row.error_rate,
      avg_ms: row.avg_ms,
      p50_ms: row.p50_ms,
      p90_ms: row.p90_ms,
      p95_ms: row.p95_ms,
      p99_ms: row.p99_ms
    }))
  );
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }));
  const link = document.createElement('a');
  link.href = url;
  const stamp = new Date(report.generated_at_ms).toISOString().slice(0, 16).replace(':', '');
  link.download = `api-monitor-${report.range}-${stamp}.csv`;
  link.click();
  URL.revokeObjectURL(url);
}
