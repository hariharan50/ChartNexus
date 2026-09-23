import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { Contribution } from '$contexts/market-breadth/types';
import PointsContribution from '../../app/routes/terminal/future-lab/analysis/components/PointsContribution';

/**
 * The contribution board, rendered.
 *
 * What is pinned here is the geometry, because it is the half that can be
 * wrong on screen without throwing: the bars carry the reading, and a bar
 * scaled against its own side instead of the shared maximum draws a perfectly
 * plausible chart that misstates which way the index moved.
 */

function row(symbol: string, points: number): Contribution {
  return {
    symbol,
    name: symbol,
    sector: 'Financials',
    last: '100',
    change_percent: '1.50',
    weight_percent: '2.50',
    points: String(points)
  };
}

const GAINERS = [row('BAJFINANCE', 16), row('RELIANCE', 8), row('SUNPHARMA', 4)];
const LOSERS = [row('INFY', -10), row('TITAN', -4)];

function board() {
  return <PointsContribution label="NIFTY 50" gainers={GAINERS} losers={LOSERS} />;
}

/** Every bar, in DOM order: up, down, up, down… */
function bars(container: HTMLElement): HTMLElement[] {
  return Array.from(container.querySelectorAll('[title]'));
}

/**
 * The rows, found by the one hook that is not a hashed CSS-module name — the
 * board is the card's single `aria-hidden` region.
 */
function rows(container: HTMLElement): Element[] {
  return Array.from(container.querySelector('[aria-hidden="true"]')!.children);
}

describe('PointsContribution', () => {
  it('adds each side up in the header', () => {
    render(<PointsContribution label="NIFTY 50" gainers={GAINERS} losers={LOSERS} />);

    expect(screen.getByText('NIFTY 50 Points Contribution')).toBeInTheDocument();
    expect(screen.getByText('+28.00')).toBeInTheDocument(); // 16 + 8 + 4
    expect(screen.getByText('−14.00')).toBeInTheDocument(); // −10 + −4
  });

  it('reports the net, which neither flanking list carries', () => {
    render(<PointsContribution label="NIFTY 50" gainers={GAINERS} losers={LOSERS} />);
    expect(screen.getByText('Net +14.00 pts')).toBeInTheDocument();
  });

  it('draws both sides against one shared scale', () => {
    /* The biggest push is 16 and the biggest drag is 10, so the red bar must
       come out at 62.5% — not at 100%, which is what a per-side scale would
       give it. */
    const { container } = render(
      <PointsContribution label="NIFTY 50" gainers={GAINERS} losers={LOSERS} />
    );

    const widths = bars(container).map((bar) => bar.style.width);
    expect(widths[0]).toContain('100.00%'); // BAJFINANCE, +16
    expect(widths[1]).toContain('62.50%'); // INFY, −10
    expect(widths[2]).toContain('50.00%'); // RELIANCE, +8
    expect(widths[3]).toContain('25.00%'); // TITAN, −4
  });

  it('mirrors the two halves so the bars meet in the middle', () => {
    /* The order of the four cells in a row *is* the butterfly: label, track,
       track, label. Emit label-before-track on both sides and the layout still
       renders — as two ordinary bar charts with a hole where the centre axis
       should be, which nothing else in this suite would catch.

       Asserted structurally rather than by class name: CSS-module names are
       hashed in this environment, so a class assertion here would pass on the
       hash and tell us nothing. */
    const cells = [...rows(render(board()).container)[0]!.children];

    expect(cells).toHaveLength(4);
    expect(cells[0]).toHaveTextContent('BAJFINANCE');
    expect(cells[1]!.querySelector('[title]')).toHaveAttribute(
      'title',
      expect.stringContaining('BAJFINANCE')
    );
    // The right half puts its track first, against the centre.
    expect(cells[2]!.querySelector('[title]')).toHaveAttribute(
      'title',
      expect.stringContaining('INFY')
    );
    expect(cells[3]).toHaveTextContent('INFY');
  });

  it('keeps the empty half of a ragged row in its columns', () => {
    /* Drop the two cells and every row below the shorter list slides across
       the centre axis, bending the whole board. */
    const ragged = rows(render(board()).container)[2]!;

    expect(ragged.children).toHaveLength(4);
    expect(ragged.children[2]!.querySelector('[title]')).toBeNull();
  });

  it('keeps a row for every member when the sides are ragged', () => {
    const { container } = render(
      <PointsContribution label="NIFTY 50" gainers={GAINERS} losers={LOSERS} />
    );

    // Three gainers against two losers: three rows, five bars.
    expect(bars(container)).toHaveLength(5);
    expect(screen.getByText('SUNPHARMA')).toBeInTheDocument();
  });

  it('gives a contribution too small to see a visible sliver', () => {
    /* A member that moved the index a hundredth of a point is present, and a
       zero-width bar would say it was not. */
    const { container } = render(
      <PointsContribution
        label="NIFTY 50"
        gainers={[row('BIG', 100), row('TINY', 0.01)]}
        losers={[]}
      />
    );

    expect(bars(container)[1]!.style.width).toContain('2px');
  });

  it('carries the full figures into each bar’s hover', () => {
    const { container } = render(
      <PointsContribution label="NIFTY 50" gainers={GAINERS} losers={LOSERS} />
    );

    expect(bars(container)[0]).toHaveAttribute(
      'title',
      'BAJFINANCE · +16.00 pts · +1.50% · 2.50% weight'
    );
  });

  it('renders nothing but the header when no member could be priced', () => {
    const { container } = render(<PointsContribution label="NIFTY 50" gainers={[]} losers={[]} />);

    expect(bars(container)).toHaveLength(0);
    expect(screen.getByText('Net 0.00 pts')).toBeInTheDocument();
  });
});
