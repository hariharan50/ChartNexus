/** Mirrors `backend/.../contexts/api_monitor/api/schemas.py`. */

export type UsageRange = '1h' | '6h' | '24h' | '7d';

export interface CallStats {
  calls: number;
  errors: number;
  error_rate: number;
  errors_by_class: Record<string, number>;
  avg_ms: number | null;
  p50_ms: number | null;
  p90_ms: number | null;
  p95_ms: number | null;
  p99_ms: number | null;
}

export interface ProviderRow extends CallStats {
  provider: string;
}

export interface EndpointRow extends CallStats {
  provider: string;
  endpoint: string;
}

export interface OriginRow extends CallStats {
  origin: string;
}

export interface AppRow extends CallStats {
  broker: string | null;
  app_label: string;
}

export type HealthStatus = 'idle' | 'healthy' | 'degraded' | 'down';

export interface ProviderHealth {
  provider: string;
  status: HealthStatus;
  recent_calls: number;
  recent_error_rate: number;
  recent_p95_ms: number | null;
  peak_per_minute: number | null;
  last_call_ms: number | null;
  last_error_ms: number | null;
  last_error: string | null;
}

export interface HistogramBucket {
  /** Upper bound in ms; `null` for "slower than the last bound". */
  le_ms: number | null;
  count: number;
}

export interface UsageFilters {
  provider: string | null;
  origin: string | null;
  endpoint: string | null;
}

export interface SeriesPoint {
  at: number;
  calls: number;
  errors: number;
  avg_ms: number | null;
  p95_ms: number | null;
  by_provider: Record<string, number>;
}

export interface RecentCall {
  at_ms: number;
  provider: string;
  endpoint: string;
  origin: string;
  method: string;
  status: number | null;
  error: string | null;
  elapsed_ms: number;
}

export interface QuotaRow {
  broker: string;
  app_label: string;
  used_today: number;
  daily_limit: number;
  window: string;
}

export interface UsageReport {
  scope: 'platform' | 'mine';
  range: UsageRange;
  step_seconds: number;
  start: number;
  end: number;
  generated_at_ms: number;
  filters: UsageFilters;
  options: { providers: string[]; origins: string[] };
  totals: CallStats & { histogram: HistogramBucket[] };
  previous: CallStats | null;
  calls_per_minute_now: number | null;
  peak_per_minute: number | null;
  health: ProviderHealth[];
  providers: ProviderRow[];
  endpoints: EndpointRow[];
  origins: OriginRow[];
  apps: AppRow[];
  series: SeriesPoint[];
  recent: RecentCall[];
  quotas: QuotaRow[];
  percentiles_are_estimates: boolean;
}

export interface AdminRoster {
  max_admins: number;
  admins: { email: string; since: string }[];
  audit: { at: string; action: string; email: string; actor: string }[];
}
