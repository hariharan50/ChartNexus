import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { FuturesRow } from '../../app/lib/contexts/futures-analytics/types';
import type { Instrument } from '../../app/lib/contexts/instrument-catalog/types';
import SidePanels from '../../app/routes/terminal/future-lab/components/SidePanels';

/**
 * The Future Lab rail.
 *
 * The regression that matters here took the whole Stocks page down with a 500:
 * an API predating the `indices` field sends instruments without it, and
 * `for (const name of entry.indices)` threw "undefined is not iterable" the
 * moment the catalog query resolved. The page rendered fine server-side — it
 * only died on the client — so nothing caught it before a user did.
 */

function row(symbol: string, changePercent: string | null, sector: string | null): FuturesRow {
  return {
    symbol,
    name: `${symbol} LIMITED`,
    price: '100',
    price_change_percent: changePercent,
    open_interest: 1000,
    oi_change_percent: '1',
    state: 'long_buildup',
    kind: 'stock',
    lot_size: 100,
    volume: 5000,
    volume_change_percent: '10',
    open_marker: null,
    sector
  };
}

function instrument(symbol: string, indices?: string[]): Instrument {
  const base: Instrument = {
    symbol,
    kind: 'stock',
    name: `${symbol} LIMITED`,
    exchange: 'NSE',
    lot_size: 100,
    tick_size: '0.05',
    strike_step: '5',
    isin: null,
    sector: 'BANKING'
  };
  return indices ? { ...base, indices } : base;
}

describe('SidePanels', () => {
  it('survives instruments that carry no index membership', () => {
    // Exactly the payload an older API returns: no `indices` key at all.
    render(
      <SidePanels
        rows={[row('HDFCBANK', '1.5', 'BANKING')]}
        instruments={[instrument('HDFCBANK')]}
        sector=""
        onSector={vi.fn()}
      />
    );

    // The category panel still renders, minus the index rows it cannot compute.
    expect(screen.getByText('FNO Stocks')).toBeInTheDocument();
    expect(screen.queryByText('NIFTY')).not.toBeInTheDocument();
  });

  it('adds an index row only when membership is known', () => {
    render(
      <SidePanels
        rows={[row('HDFCBANK', '1.5', 'BANKING'), row('SBIN', '-0.5', 'BANKING')]}
        instruments={[
          instrument('HDFCBANK', ['NIFTY50', 'BANKNIFTY']),
          instrument('SBIN', ['BANKNIFTY'])
        ]}
        sector=""
        onSector={vi.fn()}
      />
    );

    expect(screen.getByText('NIFTY')).toBeInTheDocument();
    expect(screen.getByText('BANKNIFTY')).toBeInTheDocument();
  });

  it('counts advances and declines, leaving unchanged contracts out of both', () => {
    render(
      <SidePanels
        rows={[
          row('UP', '1.5', 'BANKING'),
          row('DOWN', '-2', 'BANKING'),
          row('FLAT', '0', 'BANKING'),
          row('UNKNOWN', null, 'BANKING')
        ]}
        instruments={[]}
        sector=""
        onSector={vi.fn()}
      />
    );

    const fno = screen.getByText('FNO Stocks').closest('li');
    expect(fno).toHaveTextContent('1');
    // Flat and unmeasured contracts belong to neither column.
    expect(fno).not.toHaveTextContent('4');
  });

  it('skips sectorless rows rather than bucketing them as "Unknown"', () => {
    render(
      <SidePanels
        rows={[row('HDFCBANK', '1.5', 'BANKING'), row('NIFTY', '0.5', null)]}
        instruments={[]}
        sector=""
        onSector={vi.fn()}
      />
    );

    expect(screen.getByText('BANKING')).toBeInTheDocument();
    expect(screen.queryByText('Unknown')).not.toBeInTheDocument();
  });
});
