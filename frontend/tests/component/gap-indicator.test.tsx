import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { GapReading } from '../../app/lib/contexts/market-data/view-models';
import GapIndicatorCard from '../../app/routes/terminal/dashboard/components/GapIndicatorCard';

/**
 * The dashboard rail's gap card.
 *
 * Three states have to stay distinguishable on screen: a resolved reading, the
 * spot query still in flight, and a broker that sent a price but no opening
 * print. The last one is the one worth pinning — rendering `NaN` there, or
 * silently showing a zero gap, would read as "the market opened flat" when the
 * truth is that nobody knows where it opened.
 */
const reading: GapReading = {
  label: 'NIFTY 50',
  open: 24678.88,
  previousClose: 24540.99,
  points: 137.89,
  percent: 0.5619,
  signal: 'gap_up'
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

  it('says so when the broker supplied no opening print', () => {
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
