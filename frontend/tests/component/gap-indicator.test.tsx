import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { GapForecast } from '../../app/lib/contexts/market-data/gap-forecast';
import type { GapReading } from '../../app/lib/contexts/market-data/view-models';
import GapIndicatorCard from '../../app/routes/terminal/dashboard/components/GapIndicatorCard';

/**
 * The dashboard rail's gap card.
 *
 * Five states have to stay distinguishable on screen: the session's real
 * opening print, a simulated one, a print the auction has only just produced,
 * the pre-open *forecast*, and no reading at all. The card used to show the
 * first three identically, which is why nothing on it explained the gap
 * changing sign between refreshes — it had silently swapped a live pair for
 * the mock's.
 *
 * The forecast is the state these tests guard hardest, and the thing they
 * guard is the qualifier. An estimate of an open that has not happened,
 * rendered in the same green pill as a measurement of one that has, is the
 * single worst failure this card can have — worse than showing nothing, which
 * is what it did before the bell until now.
 *
 * Every test pins the clock. The card counts down to 09:15 off the exchange
 * clock, so a suite that did not would pass all day and fail between 08:00 and
 * the bell.
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

const forecast: GapForecast = {
  label: 'NIFTY 50',
  signal: 'gap_up',
  points: 142.3,
  percent: 0.6116,
  impliedLevel: 23407.63,
  referenceClose: 23265.33,
  source: 'live',
  asOf: new Date('2026-09-28T02:30:00Z'),
  opensAt: new Date('2026-09-28T03:45:00Z'),
  verdict: 'agree',
  pressureScore: 41.2,
  pressureBand: 'up',
  missing: 0,
  confidence: 'high',
  confidenceReason:
    'GIFT and the global composite point the same way, with every weighted market priced.'
};

/** 02:30Z is 08:00 IST on a Monday — the first minute of the pre-open watch. */
const PRE_OPEN = new Date('2026-09-28T02:30:00Z');
/** 07:00Z is 12:30 IST — mid-session, with the open long since printed. */
const MIDDAY = new Date('2026-09-28T07:00:00Z');

function at(moment: Date): void {
  vi.setSystemTime(moment);
}

describe('GapIndicatorCard', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    at(MIDDAY);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

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

  describe('before the bell', () => {
    it('calls the open at 08:00, an hour and a quarter before it happens', () => {
      // The whole point of the pre-open mode: a reader at 08:00 gets a
      // direction, not a blank card and not yesterday's gap relabelled.
      at(PRE_OPEN);
      render(<GapIndicatorCard forecast={forecast} label="NIFTY 50" />);

      expect(screen.getByText('GAP UP')).toBeInTheDocument();
      expect(screen.getByText('+142.30 (+0.61%)')).toBeInTheDocument();
      expect(screen.getByText(/Opens 09:15 IST · in 1h 15m/)).toBeInTheDocument();
    });

    it('marks the verdict as expected rather than printed', () => {
      at(PRE_OPEN);
      render(<GapIndicatorCard forecast={forecast} label="NIFTY 50" />);

      expect(screen.getByText('Expected')).toBeInTheDocument();
      expect(screen.getByText('Expected open · pre-market')).toBeInTheDocument();
      // The confirmed-print language must not leak into a forecast.
      expect(screen.queryByText(/fixed for the session/)).not.toBeInTheDocument();
    });

    it('names GIFT NIFTY as the quote it is forecasting from', () => {
      at(PRE_OPEN);
      render(<GapIndicatorCard forecast={forecast} label="NIFTY 50" />);

      expect(screen.getByText('GIFT NIFTY')).toBeInTheDocument();
      expect(screen.getByText('23,407.63')).toBeInTheDocument();
      expect(screen.getByText('23,265.33')).toBeInTheDocument();
      expect(screen.getByText(/free to move until the bell/)).toBeInTheDocument();
    });

    it('says how much the forecast is worth, and why', () => {
      at(PRE_OPEN);
      render(
        <GapIndicatorCard
          forecast={{
            ...forecast,
            confidence: 'low',
            source: 'mock',
            confidenceReason: 'Simulated — NSE IX could not be reached.'
          }}
          label="NIFTY 50"
        />
      );

      expect(screen.getByText('Low confidence')).toBeInTheDocument();
      expect(screen.getByText(/NSE IX could not be reached/)).toBeInTheDocument();
    });

    it('counts down without claiming a gap when nothing quotes the open', () => {
      // SENSEX and BANK NIFTY have no overnight contract settling to them, so
      // there is nothing to forecast from. Saying so beats an empty card and
      // beats inventing a number from NIFTY's.
      at(PRE_OPEN);
      render(<GapIndicatorCard label="BANK NIFTY" />);

      expect(screen.getByText(/Opens 09:15 IST · in 1h 15m/)).toBeInTheDocument();
      expect(screen.getByText(/no overnight contract quoting BANK NIFTY/)).toBeInTheDocument();
      expect(screen.queryByText('FLAT')).not.toBeInTheDocument();
    });

    it('drops the forecast the moment a real opening print exists', () => {
      // Both present is the hand-over instant, around 09:15. The measurement
      // wins outright: a card showing an estimate beside a print invites the
      // reader to average two things that are not the same kind of claim.
      at(MIDDAY);
      render(<GapIndicatorCard reading={reading} forecast={forecast} label="NIFTY 50" />);

      expect(screen.getByText('24,678.88')).toBeInTheDocument();
      expect(screen.queryByText('Expected')).not.toBeInTheDocument();
      expect(screen.queryByText(/Opens 09:15 IST/)).not.toBeInTheDocument();
    });

    it('shows the forecast rather than a skeleton while the spot query lands', () => {
      // The forecast arrives from a different endpoint. Blanking it because
      // the broker poll is still in flight would hide the one reading the
      // pre-open card actually has.
      at(PRE_OPEN);
      render(<GapIndicatorCard forecast={forecast} loading label="NIFTY 50" />);

      expect(screen.getByText('GAP UP')).toBeInTheDocument();
    });
  });
});
