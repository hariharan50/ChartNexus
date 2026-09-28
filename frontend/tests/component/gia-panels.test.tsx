import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { ImpliedOpen, Pressure } from '../../app/lib/contexts/global-markets/types';
import GapPressureGauge from '../../app/routes/terminal/global-index-analysis/components/GapPressureGauge';
import ImpliedOpenCard from '../../app/routes/terminal/global-index-analysis/components/ImpliedOpenCard';

/**
 * GIA's two reads.
 *
 * The claims worth pinning are the honesty ones. A composite score with no
 * visible inputs is a horoscope with a decimal point, so the waterfall must
 * show every contribution; a simulated GIFT quote that did not say it was
 * simulated would be indistinguishable from a real one by eye; and a
 * disagreement between the two reads is a finding the page must state rather
 * than average away.
 */
const pressure: Pressure = {
  score: '-34.12',
  band: 'down',
  contributions: [
    {
      key: 'SPX',
      label: 'S&P 500',
      region: 'americas',
      change_percent: '-0.755',
      weight: '1.00',
      recency: '0.652',
      points: '-13.78'
    },
    {
      key: 'NASDAQ',
      label: 'NASDAQ',
      region: 'americas',
      change_percent: '-1.131',
      weight: '0.70',
      recency: '0.652',
      points: '-14.45'
    },
    {
      key: 'NIKKEI',
      label: 'Nikkei 225',
      region: 'asia',
      change_percent: '1.33',
      weight: '0.30',
      recency: '1',
      points: '11.17'
    }
  ],
  missing: []
};

/** Intraday: NIFTY is still trading, so spot and the reference close differ. */
const implied: ImpliedOpen = {
  gift_level: '23600.00',
  gift_change: '85.00',
  gift_change_percent: '0.36',
  nifty_spot: '23446.80',
  reference_close: '23414.30',
  nifty_is_trading: true,
  basis: '153.20',
  implied_level: '23600.00',
  gap_points: '153.20',
  gap_percent: '0.65',
  signal: 'gap_up'
};

/**
 * Overnight, with the numbers from the bug report: GIFT is down on its own
 * session and below the NIFTY close the next session will open from.
 */
const settled: ImpliedOpen = {
  gift_level: '23103.50',
  gift_change: '-85.00',
  gift_change_percent: '-0.37',
  nifty_spot: '23140.50',
  reference_close: '23140.50',
  nifty_is_trading: false,
  basis: '-37.00',
  implied_level: '23103.50',
  gap_points: '-37.00',
  gap_percent: '-0.16',
  signal: 'gap_down'
};

describe('GapPressureGauge', () => {
  it('shows the score and the band it falls in', () => {
    render(<GapPressureGauge pressure={pressure} />);

    expect(screen.getByText('−34.1')).toBeInTheDocument();
    expect(screen.getByText('GAP-DOWN PRESSURE')).toBeInTheDocument();
  });

  it('itemises every market that went into the score', () => {
    render(<GapPressureGauge pressure={pressure} />);

    for (const label of ['S&P 500', 'NASDAQ', 'Nikkei 225']) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
  });

  it('shows each contribution signed, so a positive input is visible in a negative score', () => {
    render(<GapPressureGauge pressure={pressure} />);

    expect(screen.getByText('−13.8')).toBeInTheDocument();
    expect(screen.getByText('+11.2')).toBeInTheDocument();
  });

  it('names the markets it had no quote for', () => {
    // A composite built from two of nine inputs is a different claim from one
    // built on all nine, and the page has to be able to say so.
    render(<GapPressureGauge pressure={{ ...pressure, missing: ['DAX', 'FTSE'] }} />);

    expect(screen.getByText(/DAX, FTSE/)).toBeInTheDocument();
  });

  it('says nothing about missing markets when none are', () => {
    render(<GapPressureGauge pressure={pressure} />);

    expect(screen.queryByText(/the score is built without/)).not.toBeInTheDocument();
  });

  it('admits the weights are not fitted', () => {
    render(<GapPressureGauge pressure={pressure} />);

    expect(screen.getByText(/not fitted to realised gaps/)).toBeInTheDocument();
  });
});

describe('ImpliedOpenCard', () => {
  it("leads with the contract's own session move", () => {
    render(<ImpliedOpenCard implied={implied} verdict="agree" source="live" />);

    expect(screen.getByText('GIFT day change')).toBeInTheDocument();
    expect(screen.getByText('+85.00 (+0.36%)')).toBeInTheDocument();
    expect(screen.getByText('23,600.00')).toBeInTheDocument();
  });

  it('keeps the implied gap and its signal among the figures', () => {
    // Demoted from the headline, not dropped: the card is named for it and
    // the verdict below is read from its sign.
    render(<ImpliedOpenCard implied={implied} verdict="agree" source="live" />);

    expect(screen.getByText('Implied gap · GAP UP')).toBeInTheDocument();
    expect(screen.getByText('+153.20 (+0.65%)')).toBeInTheDocument();
  });

  it('names both bases, so two different discounts do not read as a contradiction', () => {
    // The gap is measured from the previous close and the basis from spot.
    // Intraday those are different numbers, and a card showing only one base
    // would look like it had contradicted itself.
    render(<ImpliedOpenCard implied={implied} verdict="agree" source="live" />);

    expect(screen.getByText('23,414.30')).toBeInTheDocument();
    expect(screen.getByText('23,446.80')).toBeInTheDocument();
    expect(screen.getByText('NIFTY prev close')).toBeInTheDocument();
    expect(screen.getByText(/gap is measured from its previous close/)).toBeInTheDocument();
  });

  it('headlines the session move, so the card reconciles with a broker screen', () => {
    // Without it, a reader comparing the card to their terminal sees GIFT
    // down 0.37% there and a gap up here, and concludes one of them is lying.
    render(<ImpliedOpenCard implied={settled} verdict="agree" source="live" />);

    expect(screen.getByText('GIFT day change')).toBeInTheDocument();
    expect(screen.getByText('−85.00 (−0.37%)')).toBeInTheDocument();
  });

  it('measures the gap from the close just printed once NIFTY has shut', () => {
    render(<ImpliedOpenCard implied={settled} verdict="agree" source="live" />);

    expect(screen.getByText('Implied gap · GAP DOWN')).toBeInTheDocument();
    expect(screen.getByText('−37.00 (−0.16%)')).toBeInTheDocument();
    expect(screen.getByText('NIFTY close')).toBeInTheDocument();
    expect(screen.getByText(/level the next session opens from/)).toBeInTheDocument();
  });

  it('drops spot and basis overnight, when both restate the gap', () => {
    render(<ImpliedOpenCard implied={settled} verdict="agree" source="live" />);

    expect(screen.queryByText('NIFTY spot')).not.toBeInTheDocument();
    expect(screen.queryByText('Basis to spot')).not.toBeInTheDocument();
  });

  it('states a disagreement rather than averaging it away', () => {
    render(<ImpliedOpenCard implied={implied} verdict="disagree" source="live" />);

    expect(screen.getByText(/disagree/)).toBeInTheDocument();
  });

  it('says the contract is simulated when it is', () => {
    render(<ImpliedOpenCard implied={implied} verdict="agree" source="mock" />);

    expect(screen.getByText(/this contract is simulated/)).toBeInTheDocument();
  });

  it('claims nothing about simulation when the feed is live', () => {
    render(<ImpliedOpenCard implied={implied} verdict="agree" source="live" />);

    expect(screen.queryByText(/simulated/)).not.toBeInTheDocument();
  });

  it('says so when there is no GIFT quote at all', () => {
    render(<ImpliedOpenCard implied={null} verdict="unknown" source="mock" />);

    const card = screen.getByLabelText('GIFT NIFTY implied open');
    expect(within(card).getByText(/cannot be read without it/)).toBeInTheDocument();
    expect(screen.queryByText('GIFT day change')).not.toBeInTheDocument();
  });
});
