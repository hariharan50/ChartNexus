import { apiFetch } from '$shared/api/client';
import type { AdminRoster, UsageFilters, UsageRange, UsageReport } from './types';

/**
 * The API latency monitor. The admin calls answer 403 for everyone else; the
 * server re-checks the role on every request, so hiding the page is a
 * convenience, not the protection.
 */

export function usageQuery(range: UsageRange, filters: Partial<UsageFilters> = {}): string {
  const params = new URLSearchParams({ range });
  for (const key of ['provider', 'origin', 'endpoint'] as const) {
    const value = filters[key];
    if (value) params.set(key, value);
  }
  return params.toString();
}

export function getPlatformUsage(
  range: UsageRange,
  filters: Partial<UsageFilters> = {}
): Promise<UsageReport> {
  return apiFetch<UsageReport>({ url: `/admin/api-monitor?${usageQuery(range, filters)}` });
}

export function getAdminRoster(): Promise<AdminRoster> {
  return apiFetch<AdminRoster>({ url: '/admin/admins' });
}

export function getMyUsage(range: UsageRange = '24h'): Promise<UsageReport> {
  return apiFetch<UsageReport>({ url: `/api-monitor/mine?range=${range}` });
}

/** Display helpers shared by the admin page and the user card. */
export function formatMs(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  if (value >= 1000) return `${(value / 1000).toFixed(value >= 10_000 ? 0 : 1)} s`;
  return `${Math.round(value)} ms`;
}

export function formatPercent(rate: number): string {
  if (rate === 0) return '0%';
  if (rate < 0.001) return '<0.1%';
  return `${(rate * 100).toFixed(rate < 0.1 ? 1 : 0)}%`;
}

export function formatCount(value: number): string {
  return new Intl.NumberFormat('en-IN').format(value);
}

export function formatRate(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  return value >= 10 ? Math.round(value).toString() : value.toFixed(1);
}

/** "12s ago", "4m ago", "2h ago" relative to `now`. */
export function formatAgo(atMs: number | null | undefined, now: number): string {
  if (!atMs) return '—';
  const seconds = Math.max(0, Math.round((now - atMs) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86_400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86_400)}d ago`;
}

export interface Delta {
  text: string;
  tone: 'good' | 'bad' | 'flat';
}

/**
 * Change against the previous period. With `higherIsWorse` a rise is red and a
 * fall green (latency, errors); without it the change is shown uncoloured
 * (traffic: more requests is neither good nor bad on its own). `points` reports
 * a rate as percentage points. `null` when there is nothing to compare with.
 */
export function delta(
  current: number | null,
  previous: number | null,
  { higherIsWorse = false, points = false }: { higherIsWorse?: boolean; points?: boolean } = {}
): Delta | null {
  if (current === null || previous === null) return null;
  if (!points && previous === 0) return null;
  const change = points ? (current - previous) * 100 : ((current - previous) / previous) * 100;
  if (Math.abs(change) < (points ? 0.05 : 0.5)) return { text: 'no change', tone: 'flat' };
  const sign = change > 0 ? '+' : '';
  const text = points ? `${sign}${change.toFixed(1)} pts` : `${sign}${Math.round(change)}%`;
  if (!higherIsWorse) return { text, tone: 'flat' };
  return { text, tone: change > 0 ? 'bad' : 'good' };
}

export function toCsv(rows: readonly Record<string, unknown>[]): string {
  const first = rows[0];
  if (!first) return '';
  const headers = Object.keys(first);
  const cell = (value: unknown): string => {
    const text = value === null || value === undefined ? '' : String(value);
    return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
  };
  const lines = rows.map((row) => headers.map((header) => cell(row[header])).join(','));
  return [headers.join(','), ...lines].join('\n');
}

export const PROVIDER_LABELS: Record<string, string> = {
  kite: 'Kite',
  fyers: 'FYERS',
  nse: 'NSE',
  nseix: 'NSE IX',
  yahoo: 'Yahoo',
  telegram: 'Telegram',
  whatsapp: 'WhatsApp',
  google: 'Google',
  other: 'Other'
};

export function providerLabel(provider: string): string {
  return PROVIDER_LABELS[provider] ?? provider;
}
