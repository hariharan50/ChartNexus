import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { MaxPainSeriesView } from '../../app/routes/terminal/options/max-pain/max-pain-data';
import IntradayMaxPain from '../../app/routes/terminal/options/max-pain/components/IntradayMaxPain';

/**
 * The Intraday Max Pain panel.
 *
 * ECharts needs a real canvas, so the chart itself is stubbed — what is worth
 * pinning here is everything *around* it: the convergence reading, and whether
 * the panel is honest about how much session it actually has. The degraded
 * `live_proxy` tier is the one that matters most: on a machine where the ingest
 * worker has not run this chart has two points, and a two-point line looks
 * exactly like a session where the pin never moved.
 */
vi.mock('../../app/routes/terminal/options/components/SeriesChart', () => ({
  default: ({ title }: { title: string }) => <div data-testid="chart">{title}</div>
}));

function view(overrides: Partial<MaxPainSeriesView> = {}): MaxPainSeriesView {
  return {
    instrument_id: 'NIFTY',
    symbol: 'NIFTY',
    expiry_date: '2026-09-29',
    lot_size: 75,
    spot: 23_223,
    open_ts: '2026-09-24T03:45:00Z',
    now_ts: '2026-09-24T05:20:00Z',
    data_quality: 'intraday',
    open_is_estimated: false,
    t: ['2026-09-24T03:45:00Z', '2026-09-24T04:30:00Z', '2026-09-24T05:20:00Z'],
    fut: [23_500, 23_300, 23_223],
    max_pain: [23_500, 23_400, 23_350],
    ...overrides
  };
}

describe('IntradayMaxPain', () => {
  it('renders the chart and the convergence reading', () => {
    render(<IntradayMaxPain view={view()} loading={false} historical={false} />);

    expect(screen.getByTestId('chart')).toHaveTextContent('Intraday Max Pain');
    expect(screen.getByText('Distance to pin')).toBeInTheDocument();
    expect(screen.getByText('−127 (−0.54%)')).toBeInTheDocument();
  });

  it('shows where the pin started and where it is now', () => {
    render(<IntradayMaxPain view={view()} loading={false} historical={false} />);

    expect(screen.getByText('−150')).toBeInTheDocument();
    expect(screen.getByText(/From 23,500 to 23,350/)).toBeInTheDocument();
  });

  it('says a pin that never moved was pinned, not that it drifted zero', () => {
    render(
      <IntradayMaxPain
        view={view({ max_pain: [23_400, 23_400, 23_400] })}
        loading={false}
        historical={false}
      />
    );

    expect(screen.getByText('Unchanged')).toBeInTheDocument();
    expect(screen.getByText(/Pinned at 23,400 all session/)).toBeInTheDocument();
  });

  it('warns that a live-proxy tier is two points, not a path', () => {
    render(
      <IntradayMaxPain
        view={view({ data_quality: 'live_proxy', open_is_estimated: true })}
        loading={false}
        historical={false}
      />
    );

    expect(screen.getByText(/two points, not a path/)).toBeInTheDocument();
  });

  it('says the open is reconstructed only when it was', () => {
    render(
      <IntradayMaxPain
        view={view({ open_is_estimated: true })}
        loading={false}
        historical={false}
      />
    );
    expect(screen.getByText(/09:15 point is reconstructed/)).toBeInTheDocument();
  });

  it('claims nothing about the open when the archive reaches the bell', () => {
    render(<IntradayMaxPain view={view()} loading={false} historical={false} />);

    expect(screen.queryByText(/reconstructed/)).not.toBeInTheDocument();
    expect(screen.queryByText(/two points/)).not.toBeInTheDocument();
  });

  it('shows an empty state rather than an axis with no data', () => {
    render(
      <IntradayMaxPain
        view={view({ data_quality: 'empty', t: [], fut: [], max_pain: [] })}
        loading={false}
        historical={false}
      />
    );

    expect(screen.queryByTestId('chart')).not.toBeInTheDocument();
    expect(screen.getByText(/No captures yet today/)).toBeInTheDocument();
  });

  it('blames the archive, not the clock, when replaying a past date', () => {
    render(
      <IntradayMaxPain
        view={view({ data_quality: 'empty', t: [], fut: [], max_pain: [] })}
        loading={false}
        historical
      />
    );

    expect(screen.getByText('No session archived for that date.')).toBeInTheDocument();
  });

  it('shows a loading state before the first payload', () => {
    render(<IntradayMaxPain view={undefined} loading historical={false} />);

    expect(screen.getByText(/Loading Intraday Max Pain/)).toBeInTheDocument();
  });
});
