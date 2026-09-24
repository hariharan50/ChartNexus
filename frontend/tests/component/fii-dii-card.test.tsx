import { render, screen } from '@testing-library/react';
import { createRoutesStub } from 'react-router';
import { describe, expect, it } from 'vitest';
import type { FlowSummary } from '../../app/lib/contexts/market-breadth/types';
import FiiDiiCard from '../../app/routes/terminal/dashboard/components/FiiDiiCard';

/**
 * The dashboard rail's participant-flow card.
 *
 * The rule the whole market-breadth context is built on is that `null` means
 * "not known", never zero. This card is the easiest place to break it: a
 * two-column grid wants a number in both cells, and coercing a missing DII line
 * to 0 would render "₹0 Cr" — a claim that institutions traded nothing, when
 * the truth is that the file has not been published. That case is pinned below.
 */
function summary(overrides: Partial<FlowSummary> = {}): FlowSummary {
  return {
    session_date: '2026-09-23',
    segments: [
      {
        segment: 'cash',
        fii: { buy: '13580.4', sell: '11962.95', net: '1617.45' },
        dii: { buy: '14404.9', sell: '12063.44', net: '2341.46' }
      }
    ],
    fii_cash_week: '-2192.54',
    fii_cash_month: '-2192.54',
    dii_cash_week: '6461.53',
    dii_cash_month: '6461.53',
    fii_cash_streak: 1,
    dii_cash_streak: 2,
    sessions: 2,
    source: 'live',
    by_participant: [],
    by_segment: [],
    imbalance: {},
    previous_session: '2026-09-22',
    next_session: null,
    index: null,
    ...overrides
  };
}

/** The card renders a `<Link>`, so it needs a router in scope. */
function renderCard(element: React.ReactElement) {
  const Stub = createRoutesStub([{ path: '/', Component: () => element }]);
  return render(<Stub initialEntries={['/']} />);
}

describe('FiiDiiCard', () => {
  it('shows each participant net for the published session', () => {
    renderCard(<FiiDiiCard summary={summary()} />);

    expect(screen.getByText('FII Cash')).toBeInTheDocument();
    expect(screen.getByText('+₹1,617 Cr')).toBeInTheDocument();
    expect(screen.getByText('+₹2,341 Cr')).toBeInTheDocument();
  });

  it('spells the same-side run out in words beside each net', () => {
    renderCard(<FiiDiiCard summary={summary()} />);

    expect(screen.getByText('1 session buying')).toBeInTheDocument();
    expect(screen.getByText('2 sessions buying')).toBeInTheDocument();
  });

  it('signs a net sale with a minus rather than dropping the direction', () => {
    const data = summary();
    data.segments[0]!.fii.net = '-1617.45';
    data.fii_cash_streak = -3;

    renderCard(<FiiDiiCard summary={data} />);

    expect(screen.getByText('−₹1,617 Cr')).toBeInTheDocument();
    expect(screen.getByText('3 sessions selling')).toBeInTheDocument();
  });

  it('names the window by what has actually been published, not a flat five days', () => {
    renderCard(<FiiDiiCard summary={summary({ sessions: 2 })} />);

    expect(screen.getByText(/Last 2 sessions/)).toBeInTheDocument();
  });

  it('caps the window label at the five sessions the backend totals', () => {
    renderCard(<FiiDiiCard summary={summary({ sessions: 60 })} />);

    expect(screen.getByText(/Last 5 sessions/)).toBeInTheDocument();
  });

  it('says a missing DII line is unpublished instead of rendering it as zero', () => {
    const data = summary();
    data.segments[0]!.dii = null;

    renderCard(<FiiDiiCard summary={data} />);

    expect(screen.getByText('Not published')).toBeInTheDocument();
    expect(screen.queryByText('₹0 Cr')).not.toBeInTheDocument();
    // The FII side is unaffected — one missing line must not blank the card.
    expect(screen.getByText('+₹1,617 Cr')).toBeInTheDocument();
  });

  it('shows neither a net nor a window total while the flow query is in flight', () => {
    renderCard(<FiiDiiCard loading />);

    expect(screen.getAllByText('Loading flow')).toHaveLength(2);
    expect(screen.queryByText(/Last \d/)).not.toBeInTheDocument();
  });

  it('links to the full participant board', () => {
    renderCard(<FiiDiiCard summary={summary()} />);

    expect(screen.getByRole('link', { name: 'Detail' })).toHaveAttribute(
      'href',
      '/future-lab/fii-dii-summary'
    );
  });
});
