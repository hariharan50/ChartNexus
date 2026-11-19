import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactElement } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type * as ApiModule from '../../app/lib/contexts/api-monitor/api';
import type { UsageReport } from '../../app/lib/contexts/api-monitor/types';
import { ApiError } from '../../app/lib/shared/api/errors';
import ApiMonitor from '../../app/routes/terminal/admin/api-monitor/route';
import MyBrokerUsage from '../../app/routes/terminal/settings/broker/MyBrokerUsage';

/**
 * The API monitor pages render what the server gives them. The two things
 * worth pinning: a non-admin gets a plain refusal (not a broken page), and the
 * numbers that arrive are the numbers shown.
 */

const stats = {
  calls: 1234,
  errors: 12,
  error_rate: 12 / 1234,
  errors_by_class: { http_5xx: 12 },
  avg_ms: 180,
  p50_ms: 120,
  p90_ms: 450,
  p95_ms: 640,
  p99_ms: 1800
};

const report: UsageReport = {
  scope: 'platform',
  range: '1h',
  step_seconds: 60,
  start: 0,
  end: 3600,
  generated_at_ms: 3_600_000,
  filters: { provider: null, origin: null, endpoint: null },
  options: { providers: ['kite'], origins: ['ingest-capture'] },
  totals: {
    ...stats,
    histogram: [
      { le_ms: 50, count: 100 },
      { le_ms: 100, count: 900 },
      { le_ms: null, count: 234 }
    ]
  },
  previous: { ...stats, calls: 1000, error_rate: 0.002, p95_ms: 500 },
  calls_per_minute_now: 21.4,
  peak_per_minute: 88,
  health: [
    {
      provider: 'kite',
      status: 'degraded',
      recent_calls: 300,
      recent_error_rate: 0.06,
      recent_p95_ms: 900,
      peak_per_minute: 88,
      last_call_ms: 3_590_000,
      last_error_ms: 3_500_000,
      last_error: 'http_5xx'
    }
  ],
  apps: [{ broker: 'kite', app_label: '...AB12', ...stats }],
  providers: [{ provider: 'kite', ...stats }],
  endpoints: [{ provider: 'kite', endpoint: '/quote', ...stats }],
  origins: [{ origin: 'ingest-capture', ...stats }],
  series: [
    { at: 0, calls: 600, errors: 2, avg_ms: 150, p95_ms: 500, by_provider: { kite: 600 } },
    { at: 60, calls: 634, errors: 10, avg_ms: 210, p95_ms: 700, by_provider: { kite: 634 } }
  ],
  recent: [
    {
      at_ms: 3_500_000,
      provider: 'kite',
      endpoint: '/quote',
      origin: 'ingest-capture',
      method: 'GET',
      status: 503,
      error: 'http_5xx',
      elapsed_ms: 1500
    },
    {
      at_ms: 1_000,
      provider: 'kite',
      endpoint: '/quote',
      origin: 'ingest-capture',
      method: 'GET',
      status: 200,
      error: null,
      elapsed_ms: 95
    }
  ],
  quotas: [
    {
      broker: 'kite',
      app_label: '...AB12',
      used_today: 1234,
      daily_limit: 200000,
      window: 'calendar day'
    }
  ],
  percentiles_are_estimates: true
};

const api = vi.hoisted(() => ({
  getPlatformUsage: vi.fn(),
  getAdminRoster: vi.fn(),
  getMyUsage: vi.fn()
}));

vi.mock('../../app/lib/contexts/api-monitor/api', async (importOriginal) => {
  const actual = await importOriginal<typeof ApiModule>();
  return { ...actual, ...api };
});

function renderWithQuery(element: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{element}</QueryClientProvider>);
}

beforeEach(() => {
  vi.clearAllMocks();
  api.getAdminRoster.mockResolvedValue({
    max_admins: 3,
    admins: [{ email: 'admin@example.com', since: '2026-11-19' }],
    audit: []
  });
});

describe('Admin API monitor', () => {
  it('refuses a non-admin plainly', async () => {
    api.getPlatformUsage.mockRejectedValue(
      new ApiError({ type: 'about:blank', title: 'Forbidden', status: 403 } as never, 403)
    );
    renderWithQuery(<ApiMonitor />);

    expect(await screen.findByRole('heading', { name: 'Admins only' })).toBeInTheDocument();
    expect(screen.queryByText('Endpoints')).not.toBeInTheDocument();
  });

  it('shows the totals, the endpoint table, quota and the admin roster', async () => {
    api.getPlatformUsage.mockResolvedValue(report);
    renderWithQuery(<ApiMonitor />);

    expect(await screen.findByText('API Latency Monitor')).toBeInTheDocument();
    expect(await screen.findAllByText('1,234')).not.toHaveLength(0);
    expect(screen.getAllByText('/quote').length).toBeGreaterThan(0);
    expect(screen.getByText('...AB12')).toBeInTheDocument();
    expect(await screen.findByText('admin@example.com')).toBeInTheDocument();
    expect(screen.getByText(/1 of 3 admin slots used/)).toBeInTheDocument();
    expect(api.getPlatformUsage).toHaveBeenCalledWith('1h', {
      provider: null,
      origin: null,
      endpoint: null
    });
  });

  it('shows provider health, the change against the previous period and the latency spread', async () => {
    api.getPlatformUsage.mockResolvedValue(report);
    renderWithQuery(<ApiMonitor />);

    expect(await screen.findByText('Degraded')).toBeInTheDocument();
    expect(screen.getByText(/Last error http_5xx/)).toBeInTheDocument();
    expect(screen.getByText('+23%')).toBeInTheDocument(); // 1234 vs 1000 requests
    expect(screen.getByText('+28%')).toBeInTheDocument(); // p95 640 vs 500 ms
    expect(screen.getByRole('list', { name: 'Latency distribution' })).toBeInTheDocument();
    expect(screen.getByText('21')).toBeInTheDocument(); // calls per minute now
  });

  it('drills into an endpoint and filters by caller through the server', async () => {
    api.getPlatformUsage.mockResolvedValue(report);
    const user = userEvent.setup();
    renderWithQuery(<ApiMonitor />);

    const row = (await screen.findAllByTitle('Open endpoint detail'))[0]!;
    await user.click(row);
    await waitFor(() =>
      expect(api.getPlatformUsage).toHaveBeenLastCalledWith('1h', {
        provider: 'kite',
        origin: null,
        endpoint: '/quote'
      })
    );
    expect(await screen.findByText('Endpoint detail')).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText('Caller'), 'ingest-capture');
    await waitFor(() =>
      expect(api.getPlatformUsage).toHaveBeenLastCalledWith('1h', {
        provider: 'kite',
        origin: 'ingest-capture',
        endpoint: '/quote'
      })
    );
  });

  it('can show only the failed calls', async () => {
    api.getPlatformUsage.mockResolvedValue(report);
    const user = userEvent.setup();
    renderWithQuery(<ApiMonitor />);

    const heading = await screen.findByRole('heading', { name: 'Recent calls' });
    const recent = heading.closest('article')!;
    expect(within(recent).getAllByRole('row')).toHaveLength(3); // header + two calls
    await user.click(within(recent).getByRole('button', { name: 'Errors' }));
    expect(within(recent).getAllByRole('row')).toHaveLength(2); // header + the one failure
  });
});

describe('My broker usage', () => {
  it('shows the caller’s own totals', async () => {
    api.getMyUsage.mockResolvedValue({ ...report, scope: 'mine', range: '24h' });
    renderWithQuery(<MyBrokerUsage />);

    expect(await screen.findByText('1,234')).toBeInTheDocument();
    expect(screen.getByText('640 ms')).toBeInTheDocument();
    expect(screen.getByText(/Kite quota today/)).toBeInTheDocument();
  });

  it('explains an empty account instead of showing zeros', async () => {
    api.getMyUsage.mockResolvedValue({
      ...report,
      scope: 'mine',
      totals: { ...stats, calls: 0, errors: 0, error_rate: 0 },
      quotas: []
    });
    renderWithQuery(<MyBrokerUsage />);

    expect(await screen.findByText(/No broker calls recorded yet/)).toBeInTheDocument();
  });
});
