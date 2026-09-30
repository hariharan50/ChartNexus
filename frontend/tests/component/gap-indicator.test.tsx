import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { GapReading } from '../../app/lib/contexts/market-data/view-models';
import GapIndicatorCard from '../../app/routes/terminal/dashboard/components/GapIndicatorCard';

/**
 * The dashboard rail's gap card.
 *
 * Four states have to stay distinguishable on screen: the session's real
 * opening print, a simulated one, the broker's pre-open placeholder, and no
 * reading at all. The card used to show the first three identically, which is
 * why nothing on it explained the gap changing sign between refreshes — it had
 * silently swapped a live pair for the mock's.
 *
 * The last state is still the one worth pinning hardest: rendering `NaN` there,
 * or a zero gap, would read as "the market opened flat" when the truth is that
 * nobody knows where it opened.
 */
const reading: GapReading = {
  label: 'NIFTY 50',
  open: 24678.88,
  previousClose: 24540.99,
  points: 137.89,
  percent: 0.5619,
  signal: 'gap_up',
  source: 'live',
  observedAt: new Date('2026-09-28T03:45:30Z'),
  settled: true
};

describe('GapIndicatorCard', () => {
  it('names the focused index and shows the verdict with a signed gap', () => {
    render(<GapIndicatorCard reading={reading} label="NIFTY 50" />);

    expect(screen.getByText('NIFTY 50 Gap')).toBeInTheDocument();
    expect(screen.getByText('GAP UP')).toBeInTheDocument();
    expect(screen.getByText('24,678.88')).toBeInTheDocument();
    expect(screen.getByText('24,540.99')).toBeInTheDocument();
    expect(screen.getByText('+137.89 (+0.56%)')).toBeInTheDocument();
  });

  it('marks a negative gap down and signs both figures with a minus', () => {
    render(
      <GapIndicatorCard
        reading={{ ...reading, points: -137.89, percent: -0.5619, signal: 'gap_down' }}
        label="NIFTY 50"
      />
    );

    expect(screen.getByText('GAP DOWN')).toBeInTheDocument();
    expect(screen.getByText('−137.89 (−0.56%)')).toBeInTheDocument();
  });

  it('says when the opening print was taken, and that it will not move again', () => {
    // 03:45:30Z is 09:15:30 IST. The time is the point: it tells the reader the
    // figure is a print from the open rather than something recomputed on each
    // fifteen-second poll, which is what it used to be.
    render(<GapIndicatorCard reading={reading} label="NIFTY 50" />);

    expect(screen.getByText(/09:15 IST/)).toBeInTheDocument();
    expect(screen.getByText(/fixed for the session/)).toBeInTheDocument();
  });

  it('still qualifies the open as the broker’s print rather than the exchange’s', () => {
    render(<GapIndicatorCard reading={reading} label="NIFTY 50" />);

    expect(screen.getByText(/an approximate open/)).toBeInTheDocument();
  });

  it('calls a simulated gap simulated rather than dressing it as a print', () => {
    render(<GapIndicatorCard reading={{ ...reading, source: 'mock' }} label="NIFTY 50" />);

    expect(screen.getByText(/Simulated/)).toBeInTheDocument();
    expect(screen.queryByText(/fixed for the session/)).not.toBeInTheDocument();
  });

  it('shows a cached reading as the last live one, with its time', () => {
    render(<GapIndicatorCard reading={{ ...reading, source: 'cached' }} label="NIFTY 50" />);

    expect(screen.getByText(/Last live reading, taken at 09:15 IST/)).toBeInTheDocument();
  });

  it('flags a pre-open placeholder as provisional', () => {
    // Brokers fill the open with the previous session's figure until the
    // auction runs. Rendering that as the opening print is the failure.
    render(<GapIndicatorCard reading={{ ...reading, settled: false }} label="NIFTY 50" />);

    expect(screen.getByText(/Provisional/)).toBeInTheDocument();
  });

  it('carries no qualifier when there is no reading to qualify', () => {
    render(<GapIndicatorCard label="BANK NIFTY" />);

    expect(screen.queryByText(/fixed for the session/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Simulated/)).not.toBeInTheDocument();
  });

  it('says so when the session has no opening print yet', () => {
    render(<GapIndicatorCard label="BANK NIFTY" />);

    expect(screen.getByText('BANK NIFTY Gap')).toBeInTheDocument();
    expect(screen.getByText(/Gap unavailable/)).toBeInTheDocument();
    expect(screen.queryByText('FLAT')).not.toBeInTheDocument();
  });

  it('shows no verdict while the spot query is still loading', () => {
    render(<GapIndicatorCard loading label="NIFTY 50" />);

    expect(screen.queryByText('GAP UP')).not.toBeInTheDocument();
    expect(screen.queryByText(/Gap unavailable/)).not.toBeInTheDocument();
  });
});
