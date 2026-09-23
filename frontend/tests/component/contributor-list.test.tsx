import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { Contribution } from '$contexts/market-breadth/types';
import ContributorList from '../../app/routes/terminal/future-lab/analysis/components/ContributorList';

/**
 * A side of the index, listed.
 *
 * The count in the heading is the day's breadth, so it has to be the number of
 * rows actually rendered and not a truncated view of them — and the change
 * column has to keep its sign, because an unsigned "1.09%" beside a red
 * heading is the same string as a gain.
 */

function row(symbol: string, last: string, changePercent: string): Contribution {
  return {
    symbol,
    name: symbol,
    sector: 'IT',
    last,
    change_percent: changePercent,
    weight_percent: '2.50',
    points: '1.00'
  };
}

const LOSERS = [row('INFY', '1018.20', '-1.09'), row('TCS', '2081.70', '-1.11')];

describe('ContributorList', () => {
  it('counts the members it is showing', () => {
    render(<ContributorList title="Negative Contributors" rows={LOSERS} side="down" />);

    expect(screen.getByText('Negative Contributors')).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument();
  });

  it('shows each member with its price and its own move', () => {
    render(<ContributorList title="Negative Contributors" rows={LOSERS} side="down" />);

    const infy = screen.getByText('INFY').closest('tr')!;
    expect(within(infy).getByText('1,018.20')).toBeInTheDocument();
    // Signed, always: the sign is what makes it a fall rather than a rise.
    expect(within(infy).getByText('-1.09%')).toBeInTheDocument();
  });

  it('says so rather than showing an empty table', () => {
    render(<ContributorList title="Negative Contributors" rows={[]} side="down" />);

    expect(screen.getByText('0')).toBeInTheDocument();
    expect(screen.getByText(/No member moved the index down today/)).toBeInTheDocument();
  });
});
