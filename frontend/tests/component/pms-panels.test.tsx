import { render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type {
  ExpectedMove,
  HeadlineCard,
  Levels,
  Regime,
  SectionStatus,
  Volatility
} from '../../app/lib/contexts/pre-market/types';
import { VolatilityCard } from '../../app/routes/terminal/pre-market-screener/components/ContextPanels';
import ExpectedMoveCard from '../../app/routes/terminal/pre-market-screener/components/ExpectedMoveCard';
import HeadlineCards from '../../app/routes/terminal/pre-market-screener/components/HeadlineCards';
import LevelLadder from '../../app/routes/terminal/pre-market-screener/components/LevelLadder';
import RegimeScorecard from '../../app/routes/terminal/pre-market-screener/components/RegimeScorecard';
import SectionUnavailable from '../../app/routes/terminal/pre-market-screener/components/SectionUnavailable';

/**
 * The PMS panels.
 *
 * These assert the page's honesty rules rather than its markup, because those
 * are the parts that would be silently wrong: a percentile printed off eleven
 * sessions, a score that looks confident on three inputs, an expected move
 * blended out of three incompatible measures, a GIFT quote rendered where a
 * print belongs, and a dead panel that blanks instead of saying why.
 */

const card = (over: Partial<HeadlineCard> = {}): HeadlineCard => ({
  symbol: 'NIFTY',
  label: 'NIFTY 50',
  price: '25482.00',
  change: '96.00',
  change_percent: '0.38',
  previous_close: '25386.00',
  gap: null,
  implied_gap: null,
  breadth_tracked: true,
  source: 'live',
  ...over
});

const gap = (over = {}) => ({
  points: '189.00',
  percent: '0.74',
  bucket: 'gap_up' as const,
  basis: 'atr' as const,
  atr_multiple: 0.86,
  reference_close: '25386.00',
  ...over
});

const regime: Regime = {
  score: 68.4,
  band: 'bullish',
  confidence: 'high',
  inputs_present: 8,
  inputs_total: 9,
  axes: [
    { axis: 'trend', label: 'Trend', stance: 'bullish', points: 12, resolved: true, factors: [] },
    {
      axis: 'breadth',
      label: 'Breadth',
      stance: 'neutral',
      points: 0,
      resolved: false,
      factors: []
    }
  ],
  factors: [
    {
      key: 'ema_stack',
      label: 'EMA stack',
      axis: 'trend',
      stance: 'bullish',
      points: 12,
      reading: '20 > 50 > 100 > 200',
      note: null
    },
    {
      key: 'adx',
      label: 'Trend strength',
      axis: 'trend',
      stance: 'bearish',
      points: -2,
      reading: 'ADX 14.2',
      note: 'Below 20 — range, not trend.'
    }
  ]
};

const levels: Levels = {
  spot: 25482,
  pivot: 25405,
  r1: 25600,
  r2: 25815,
  r3: 26000,
  s1: 25190,
  s2: 24995,
  s3: 24800,
  cpr_top: 25420,
  cpr_bottom: 25390,
  cpr_width_percent: 0.12,
  prior_day_high: 25620,
  prior_day_low: 25210,
  prior_day_close: 25386,
  week: { high: 25700, low: 25100, bars: 5 },
  month: null,
  year: { high: 26200, low: 21400, bars: 11 },
  ladder: [
    {
      label: 'R1',
      price: 25600,
      origin: 'pivot',
      side: 'above',
      distance_points: 118,
      distance_percent: 0.46,
      distance_atr: 0.54
    },
    {
      label: 'Call wall',
      price: 25610,
      origin: 'option_wall',
      side: 'above',
      distance_points: 128,
      distance_percent: 0.5,
      distance_atr: 0.58
    },
    {
      label: 'S1',
      price: 25190,
      origin: 'pivot',
      side: 'below',
      distance_points: -292,
      distance_percent: -1.15,
      distance_atr: -1.33
    }
  ],
  clusters: [{ price: 25605, labels: ['R1', 'Call wall'], origins: ['pivot', 'option_wall'] }],
  nearest_above: null,
  nearest_below: null
};

const move: ExpectedMove = {
  spot: 25482,
  straddle: { basis: 'straddle', points: 148, percent: 0.58, upper: 25630, lower: 25334 },
  vix: { basis: 'vix', points: 96, percent: 0.38, upper: 25578, lower: 25386 },
  atr: { basis: 'atr', points: 219, percent: 0.86, upper: 25701, lower: 25263 },
  days_to_expiry: 3,
  note: 'Options are pricing a narrower move than the index has been making — the range is cheap relative to realised movement.'
};

const vol = (over: Partial<Volatility> = {}): Volatility => ({
  india_vix: '13.82',
  india_vix_change_percent: '-4.21',
  vix_percentile: null,
  vix_sample_sessions: 0,
  atm_iv: '13.80',
  iv_percentile: '38',
  ...over
});

describe('HeadlineCards', () => {
  it('separates a realised gap from a GIFT-quoted one', () => {
    // Before 09:15 there is no open. Rendering a contract's quote where a
    // print belongs would let an opinion be read as a fact.
    render(
      <HeadlineCards cards={[card({ implied_gap: gap() })]} focus="NIFTY" onFocus={vi.fn()} />
    );

    expect(screen.getByText('GIFT-implied')).toBeInTheDocument();
    expect(screen.queryByText('Opened at')).not.toBeInTheDocument();
  });

  it('says so when nothing has opened and nothing is quoted', () => {
    render(<HeadlineCards cards={[card()]} focus="NIFTY" onFocus={vi.fn()} />);

    expect(screen.getByText('No open yet')).toBeInTheDocument();
    expect(screen.getByText('Awaiting the open')).toBeInTheDocument();
  });

  it('shows the gap in ATR multiples, not percent alone', () => {
    // Sixty points is a shrug on a wide-range index and an event on a quiet
    // one; only the multiple carries that across three instruments.
    render(<HeadlineCards cards={[card({ gap: gap() })]} focus="NIFTY" onFocus={vi.fn()} />);

    expect(screen.getByText(/0\.86× ATR/)).toBeInTheDocument();
  });

  it('names an index whose breadth is not tracked', () => {
    render(
      <HeadlineCards
        cards={[card({ symbol: 'SENSEX', label: 'SENSEX', breadth_tracked: false })]}
        focus="NIFTY"
        onFocus={vi.fn()}
      />
    );

    expect(screen.getByText('Breadth not tracked')).toBeInTheDocument();
  });
});

describe('RegimeScorecard', () => {
  it('shows every factor with the figure it was read from', () => {
    // A composite whose inputs cannot be inspected is a horoscope with a
    // decimal point.
    render(<RegimeScorecard regime={regime} />);

    expect(screen.getByText('EMA stack')).toBeInTheDocument();
    expect(screen.getByText('20 > 50 > 100 > 200')).toBeInTheDocument();
    expect(screen.getByText('ADX 14.2')).toBeInTheDocument();
  });

  it('states how much of the input set actually answered', () => {
    render(<RegimeScorecard regime={regime} />);

    expect(screen.getByText(/of 9 inputs/)).toBeInTheDocument();
    expect(screen.getByText(/full input set/)).toBeInTheDocument();
  });

  it('warns when the score rests on a thin sample of inputs', () => {
    render(<RegimeScorecard regime={{ ...regime, inputs_present: 2, confidence: 'thin' }} />);

    expect(screen.getByText(/indicative only/)).toBeInTheDocument();
  });

  it('keeps an unresolved axis visible rather than dropping it', () => {
    // A six-axis card that silently becomes four looks complete when it is not.
    render(<RegimeScorecard regime={regime} />);

    expect(screen.getByText('Breadth')).toBeInTheDocument();
  });

  it('refuses to read as a trade signal', () => {
    render(<RegimeScorecard regime={regime} />);

    expect(screen.getByText(/not a trade signal/)).toBeInTheDocument();
    expect(screen.getByText(/unfitted/)).toBeInTheDocument();
  });
});

describe('LevelLadder', () => {
  it('leads with confluence across different methods', () => {
    render(<LevelLadder levels={levels} />);

    const block = screen.getByText('Where independent methods agree').closest('div');
    expect(block).not.toBeNull();
    expect(within(block as HTMLElement).getByText(/Pivot · Option OI/)).toBeInTheDocument();
  });

  it('names the method behind every level', () => {
    render(<LevelLadder levels={levels} />);

    expect(screen.getAllByText('Pivot').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Option OI').length).toBeGreaterThan(0);
  });

  it('marks where spot sits in the ladder', () => {
    render(<LevelLadder levels={levels} />);

    expect(screen.getByText('Spot')).toBeInTheDocument();
  });

  it('presents option OI as positioning, not as levels that hold', () => {
    render(<LevelLadder levels={levels} />);

    expect(screen.getByText(/not levels that will hold/)).toBeInTheDocument();
  });
});

describe('ExpectedMoveCard', () => {
  it('shows all three measures and blends none of them', () => {
    render(<ExpectedMoveCard move={move} />);

    expect(screen.getByText('Straddle (priced)')).toBeInTheDocument();
    expect(screen.getByText('India VIX (implied)')).toBeInTheDocument();
    expect(screen.getByText('ATR (realised)')).toBeInTheDocument();
    expect(screen.getByText(/an average of them would have no meaning/)).toBeInTheDocument();
  });

  it('surfaces the disagreement rather than resolving it', () => {
    render(<ExpectedMoveCard move={move} />);

    expect(screen.getByText(/narrower move than the index has been making/)).toBeInTheDocument();
  });

  it("names the straddle's horizon, which is not today alone", () => {
    render(<ExpectedMoveCard move={move} />);

    expect(screen.getByText(/3 sessions to expiry/)).toBeInTheDocument();
  });

  it('says so when no measure could be computed', () => {
    render(
      <ExpectedMoveCard move={{ ...move, straddle: null, vix: null, atr: null, note: null }} />
    );

    expect(screen.getByText(/No measure of the expected move/)).toBeInTheDocument();
  });
});

describe('VolatilityCard', () => {
  it('reports the sample size instead of a percentile it cannot support', () => {
    render(<VolatilityCard read={vol({ vix_sample_sessions: 11 })} />);

    expect(screen.getByText(/11 sessions stored so far/)).toBeInTheDocument();
  });

  it('prints the percentile with its sample size once there is enough', () => {
    render(<VolatilityCard read={vol({ vix_percentile: 34.2, vix_sample_sessions: 240 })} />);

    expect(screen.getByText(/34\.2 over 240 sessions/)).toBeInTheDocument();
  });
});

describe('SectionUnavailable', () => {
  it('renders the reason verbatim so it can be acted on', () => {
    // "SENSEX has no weight table" is permanent; "the chain timed out" is worth
    // a refresh. A generic "no data" says neither.
    const status: SectionStatus = {
      availability: 'unavailable',
      reason: 'SENSEX has no constituent weight table, so participation cannot be counted for it.'
    };

    render(<SectionUnavailable status={status} />);

    expect(screen.getByText(/no constituent weight table/)).toBeInTheDocument();
  });

  it('renders nothing when the panel is fine', () => {
    const { container } = render(
      <SectionUnavailable status={{ availability: 'ok', reason: null }} />
    );

    expect(container).toBeEmptyDOMElement();
  });
});
