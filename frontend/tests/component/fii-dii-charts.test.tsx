import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import type { FlowSummary, OiGroup, OiRow } from '../../app/lib/contexts/market-breadth/types';
import FiiDiiCharts from '../../app/routes/terminal/future-lab/analysis/components/FiiDiiCharts';
import FiiDiiGuide from '../../app/routes/terminal/future-lab/analysis/components/FiiDiiGuide';

/**
 * The FII/DII chart view and its guide.
 *
 * The split bars are plain CSS, so nothing needs stubbing — which is half the
 * reason they replaced the gauge. What is pinned here is that the headline is
 * stated in words rather than left as a ratio to decode, and that a session
 * with no long/short legs says so instead of drawing an all-short bar.
 */

function row(over: Partial<OiRow> = {}): OiRow {
  return {
    participant: 'fii',
    segment: 'index_futures',
    net: -302_908,
    previous_net: -290_546,
    change: -12_362,
    legs: {
      long: 40_257,
      short: 343_165,
      call_long: null,
      call_short: null,
      put_long: null,
      put_short: null,
      total: 383_422
    },
    ...over
  };
}

function summary(rows: OiRow[]): FlowSummary {
  const groups: OiGroup[] = [{ key: 'fii', rows, net: 0, change: 0 }];
  return {
    session_date: '2026-09-24',
    segments: [
      {
        segment: 'cash',
        fii: { buy: '13580', sell: '11963', net: '1617' },
        dii: { buy: '14405', sell: '12063', net: '2341' }
      }
    ],
    fii_cash_week: '-2192',
    fii_cash_month: '-2192',
    dii_cash_week: '6461',
    dii_cash_month: '6461',
    fii_cash_streak: 1,
    dii_cash_streak: 2,
    sessions: 2,
    source: 'live',
    by_participant: groups,
    by_segment: groups,
    imbalance: {},
    previous_session: null,
    next_session: null,
    index: null
  };
}

describe('FiiDiiCharts', () => {
  it('states the headline positioning in words, not just a ratio', () => {
    render(<FiiDiiCharts data={summary([row()])} />);

    expect(screen.getByText(/8\.5 shorts for every long/)).toBeInTheDocument();
  });

  it('shows the split as a proportion anyone can picture', () => {
    // 40,257 of a 383,422 book is 10% long — the number the bar is drawn from,
    // and a more direct reading than the 0.12 ratio behind it.
    render(<FiiDiiCharts data={summary([row()])} />);

    expect(screen.getByRole('img', { name: 'FII: 10% long, 90% short' })).toBeInTheDocument();
  });

  it('shows the two legs the split came from', () => {
    render(<FiiDiiCharts data={summary([row()])} />);

    expect(screen.getByText('40,257')).toBeInTheDocument();
    expect(screen.getByText('3,43,165')).toBeInTheDocument();
  });

  it('names a participant the file did not price rather than drawing it flat', () => {
    // A zero-width long side is indistinguishable from a fully short book.
    render(<FiiDiiCharts data={summary([row()])} />);

    expect(screen.getAllByText('not published').length).toBeGreaterThan(0);
  });

  it('says so rather than drawing bars when no participant has legs', () => {
    const legs = { ...row().legs!, long: null, short: null };

    render(<FiiDiiCharts data={summary([row({ legs })])} />);

    expect(screen.getByText(/No long\/short legs published/)).toBeInTheDocument();
  });

  it('keeps the matrix at a full 4x4 even when one pair is published', () => {
    render(<FiiDiiCharts data={summary([row()])} />);

    // Four participant labels down the side, four segment labels across.
    for (const label of ['FII', 'DII', 'Pro', 'Client']) {
      expect(screen.getAllByText(label).length).toBeGreaterThan(0);
    }
  });

  it('keeps value and positions in separate panels with their own units', () => {
    render(<FiiDiiCharts data={summary([row()])} />);

    expect(screen.getByText(/Rupees crore traded on the day/)).toBeInTheDocument();
    expect(screen.getByText(/Net contracts held/)).toBeInTheDocument();
  });
});

describe('FiiDiiGuide', () => {
  it('opens on the procedure it exists to teach', async () => {
    render(<FiiDiiGuide onClose={() => {}} />);

    expect(screen.getByRole('dialog')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('tab', { name: 'How to read it' }));

    expect(screen.getByText(/Start with the cash line/)).toBeInTheDocument();
  });

  it('is honest about what the file cannot answer', async () => {
    render(<FiiDiiGuide onClose={() => {}} />);

    await userEvent.click(screen.getByRole('tab', { name: 'What it cannot tell you' }));

    expect(screen.getByText(/It is not live/)).toBeInTheDocument();
    expect(screen.getByText(/Hedges look like views/)).toBeInTheDocument();
  });

  it('closes on Escape', async () => {
    const onClose = vi.fn();
    render(<FiiDiiGuide onClose={onClose} />);

    await userEvent.keyboard('{Escape}');

    expect(onClose).toHaveBeenCalled();
  });

  it('closes on the close button', async () => {
    const onClose = vi.fn();
    render(<FiiDiiGuide onClose={onClose} />);

    await userEvent.click(screen.getAllByRole('button', { name: 'Close' })[1]!);

    expect(onClose).toHaveBeenCalled();
  });

  it('locks the page behind it from scrolling, and gives it back', () => {
    const { unmount } = render(<FiiDiiGuide onClose={() => {}} />);
    expect(document.body.style.overflow).toBe('hidden');

    unmount();
    expect(document.body.style.overflow).not.toBe('hidden');
  });
});
