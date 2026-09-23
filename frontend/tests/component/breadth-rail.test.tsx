import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import type { IndexHeader, SectorRow } from '$contexts/market-breadth/types';
import BreadthControls from '../../app/routes/terminal/future-lab/analysis/components/BreadthControls';
import BreadthRail from '../../app/routes/terminal/future-lab/analysis/components/BreadthRail';

/**
 * The rail and the controls above it.
 *
 * Two universes share this column, and the page's honesty rests on them being
 * told apart: an index row counts a published index against published weights,
 * a sector row counts every F&O name the catalog classifies there. The other
 * thing pinned here is the weighted toggle, which must stay visible and inert
 * on a sector rather than vanishing as you move down the list.
 */

const HEADER = {
  index: 'NIFTY50',
  level: '23437.10',
  previous_close: '23330.00',
  change_absolute: '107.10',
  change_percent: '0.46',
  covered: 49,
  universe: 50,
  covered_weight_percent: '99.2',
  source: 'live',
  as_of: null,
  basis: 'futures'
} as IndexHeader;

function sector(name: string, advancing: number, declining: number): SectorRow {
  return {
    sector: name,
    count: {
      advancing,
      declining,
      unchanged: 0,
      unpriced: 0,
      ratio: null,
      advancing_percent: null,
      net: advancing - declining
    },
    mean_change_percent: '-1.01',
    members: advancing + declining,
    rows: []
  };
}

const SECTORS = [sector('IT', 2, 11), sector('METAL', 9, 2)];

describe('BreadthRail', () => {
  it('shows an index its level and a sector its breadth', () => {
    /* A sector has no index in this app, so where the level goes it shows the
       one thing it genuinely has. */
    render(
      <BreadthRail
        scope={{ index: 'NIFTY50', sector: null }}
        onScope={vi.fn()}
        sectors={SECTORS}
        header={HEADER}
        loading={false}
      />
    );

    const nifty = screen.getByText('NIFTY 50').closest('tr')!;
    expect(within(nifty).getByText('23,437.10')).toBeInTheDocument();

    const it = screen.getByText('IT').closest('tr')!;
    expect(within(it).getByText('2')).toBeInTheDocument();
    expect(within(it).getByText('11')).toBeInTheDocument();
  });

  it('names the universe each group is counted over', () => {
    render(
      <BreadthRail
        scope={{ index: 'NIFTY50', sector: null }}
        onScope={vi.fn()}
        sectors={SECTORS}
        header={HEADER}
        loading={false}
      />
    );
    expect(screen.getByText('F&O')).toBeInTheDocument();
  });

  it('reports the picked scope, index or sector', async () => {
    const onScope = vi.fn();
    render(
      <BreadthRail
        scope={{ index: 'NIFTY50', sector: null }}
        onScope={onScope}
        sectors={SECTORS}
        header={HEADER}
        loading={false}
      />
    );

    await userEvent.click(screen.getByText('METAL'));
    expect(onScope).toHaveBeenCalledWith({ index: 'NIFTY50', sector: 'METAL' });

    await userEvent.click(screen.getByText('BANK NIFTY'));
    expect(onScope).toHaveBeenCalledWith({ index: 'BANKNIFTY', sector: null });
  });

  it('marks the selection so the reader knows what they are looking at', () => {
    render(
      <BreadthRail
        scope={{ index: 'NIFTY50', sector: 'IT' }}
        onScope={vi.fn()}
        sectors={SECTORS}
        header={HEADER}
        loading={false}
      />
    );

    expect(screen.getByText('IT')).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByText('NIFTY 50')).toHaveAttribute('aria-pressed', 'false');
  });
});

describe('BreadthControls', () => {
  function controls(over: Partial<Parameters<typeof BreadthControls>[0]> = {}) {
    return (
      <BreadthControls
        interval="5m"
        onInterval={vi.fn()}
        mode="live"
        onMode={vi.fn()}
        date="2026-09-22"
        onDate={vi.fn()}
        sessions={['2026-09-22', '2026-09-21']}
        weighted={false}
        onWeighted={vi.fn()}
        weightedAvailable
        {...over}
      />
    );
  }

  it('disables the weighted view where there are no weights', () => {
    /* Visible and inert, not gone: a control that disappears as you move down
       the rail reads as a bug rather than as a limit. */
    render(controls({ weightedAvailable: false }));

    const toggle = screen.getByRole('checkbox');
    expect(toggle).toBeDisabled();
    expect(toggle).not.toBeChecked();
  });

  it('will not offer Historical when nothing has been captured', () => {
    render(controls({ sessions: [] }));
    expect(screen.getByText('Historical')).toBeDisabled();
  });

  it('offers the session picker only in historical mode', async () => {
    const { rerender } = render(controls());
    expect(screen.queryByLabelText('Archived session')).not.toBeInTheDocument();

    rerender(controls({ mode: 'historical' }));
    expect(screen.getByLabelText('Archived session')).toBeInTheDocument();
  });
});
