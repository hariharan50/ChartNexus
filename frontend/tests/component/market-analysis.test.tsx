import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createRoutesStub } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Guidance, GuidanceHistory } from '../../app/lib/contexts/signals/types';
import {
  bandExplainer,
  holdBand,
  horizonConsensus,
  levelLadder,
  scaffoldPoints
} from '../../app/routes/terminal/ai-console/ai-console-data';
import MarketAnalysis from '../../app/routes/terminal/ai-console/analysis/route';

/**
 * Market Analysis: the pure view-models behind the new panels, and the page
 * rendering them. The cases pin what the redesign is for — all three horizons
 * readable at once, *why* a call is HOLD, which way each driver pushes, and an
 * explained empty scaffold instead of four dashes.
 */

const api = vi.hoisted(() => ({
  getGuidance: vi.fn(),
  getGuidanceHistory: vi.fn()
}));

vi.mock('../../app/lib/contexts/signals/api', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return { ...actual, ...api };
});

const guidance: Guidance = {
  symbol: 'NIFTY',
  decision: 'HOLD',
  confidence: 11,
  score: 0.12,
  regime: 'trending_up',
  provenance: 'live',
  is_actionable: true,
  rationale: 'NIFTY — intraday: HOLD (11%), end of day: BUY (18%), swing: BUY (24%).',
  expiry_ref: null,
  warnings: ['Low confidence: treat as context, not a signal.'],
  horizons: [
    {
      horizon: 'intraday',
      decision: 'HOLD',
      probability: 0.56,
      confidence: 11,
      drivers: ['gex_sign', 'range_pos', 'rsi_norm'],
      factors: [
        { name: 'gex_sign', impact: 0.42 },
        { name: 'range_pos', impact: -0.21 },
        { name: 'rsi_norm', impact: 0.1 }
      ],
      band: 0.07
    },
    {
      horizon: 'end_of_day',
      decision: 'BUY',
      probability: 0.62,
      confidence: 18,
      drivers: ['ret_20'],
      factors: [{ name: 'ret_20', impact: 0.3 }],
      band: 0.06
    },
    {
      horizon: 'swing',
      decision: 'BUY',
      probability: 0.66,
      confidence: 24,
      drivers: ['daily_ret_3'],
      band: 0.06
    }
  ],
  context: { india_vix: 16.11, india_vix_change_percent: 3.5, pcr: 1.18 },
  levels: {
    spot: 25514,
    support: 25500,
    resistance: 25540,
    max_pain: 25400,
    gamma_flip: 25540,
    call_wall: 25500,
    put_wall: 25300
  },
  scaffold: { entry: null, stop: null, target: null, risk_reward: null, suggested_contract: null },
  coverage: 0.82
};

const history: GuidanceHistory = {
  symbol: 'NIFTY',
  items: [
    {
      generated_at: new Date().toISOString(),
      symbol: 'NIFTY',
      decision: 'HOLD',
      confidence: 11,
      score: 0.1,
      provenance: 'live'
    },
    {
      generated_at: new Date(Date.now() - 60_000).toISOString(),
      symbol: 'NIFTY',
      decision: 'BUY',
      confidence: 31,
      score: 0.3,
      provenance: 'live'
    }
  ]
};

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Stub = createRoutesStub([{ path: '/ai-console', Component: MarketAnalysis }]);
  return render(
    <QueryClientProvider client={client}>
      <Stub initialEntries={['/ai-console']} />
    </QueryClientProvider>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  api.getGuidance.mockResolvedValue(guidance);
  api.getGuidanceHistory.mockResolvedValue(history);
});

describe('view-models', () => {
  it('reads the horizon consensus', () => {
    expect(horizonConsensus(guidance.horizons).label).toBe('2 of 3: BUY');
    expect(horizonConsensus(guidance.horizons).averageConfidence).toBe(18);
    const all = horizonConsensus([
      { decision: 'SELL', confidence: 40 },
      { decision: 'SELL', confidence: 50 }
    ]);
    expect(all.agree).toBe(true);
    expect(all.label).toBe('All 2 horizons: SELL');
    expect(
      horizonConsensus([
        { decision: 'BUY', confidence: 1 },
        { decision: 'SELL', confidence: 1 },
        { decision: 'HOLD', confidence: 1 }
      ]).label
    ).toBe('Horizons split');
  });

  it('explains the HOLD band', () => {
    const band = holdBand(0.07);
    expect(band?.low).toBeCloseTo(0.43);
    expect(band?.high).toBeCloseTo(0.57);
    expect(bandExplainer(0.56, band)).toMatch(/needs above 57% for BUY or below 43% for SELL/);
    expect(bandExplainer(0.6, band)).toMatch(/calls BUY/);
    expect(holdBand(null)).toBeNull();
    expect(holdBand(0.6)).toBeNull();
  });

  it('orders the ladder highest first and flags the nearest level', () => {
    const ladder = levelLadder(guidance.levels);
    expect(ladder.map((row) => row.key)).toEqual([
      'resistance',
      'gamma_flip',
      'spot',
      'call_wall',
      'support',
      'max_pain',
      'put_wall'
    ]);
    const nearest = ladder.filter((row) => row.nearest);
    expect(nearest).toHaveLength(1);
    expect(nearest[0]?.key).toBe('call_wall'); // 14 points below spot
    expect(nearest[0]?.points).toBe(-14);
  });

  it('measures scaffold risk and reward only when every leg exists', () => {
    expect(scaffoldPoints(guidance.scaffold)).toBeNull();
    expect(
      scaffoldPoints({
        entry: 100,
        stop: 90,
        target: 125,
        risk_reward: 2.5,
        suggested_contract: null
      })
    ).toEqual({ risk: 10, reward: 25 });
  });
});

describe('Market Analysis page', () => {
  it('shows all three horizons at once with their calls', async () => {
    renderPage();
    const strip = await screen.findByRole('tablist', { name: 'Signal horizon' });
    const tabs = within(strip).getAllByRole('tab');
    expect(tabs).toHaveLength(3);
    expect(within(tabs[0]!).getByText('HOLD')).toBeInTheDocument();
    expect(within(tabs[1]!).getByText('BUY')).toBeInTheDocument();
    expect(within(tabs[2]!).getByText('24% sure')).toBeInTheDocument();
    expect(screen.getByText('2 of 3: BUY')).toBeInTheDocument();
  });

  it('explains a HOLD, shows signed drivers and coverage', async () => {
    renderPage();
    expect(await screen.findByText(/Inside the HOLD band/)).toBeInTheDocument();
    expect(screen.getByText('+0.42')).toBeInTheDocument();
    expect(screen.getByText('−0.21')).toBeInTheDocument();
    expect(screen.getByText('Data coverage 82%')).toBeInTheDocument();
    expect(screen.getByRole('meter', { name: 'Probability of an up-move' })).toHaveAttribute(
      'aria-valuenow',
      '56'
    );
  });

  it('falls back to driver names when a horizon has no impacts', async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole('tab', { name: /Swing/ }));
    expect(screen.getByText('3-day return')).toBeInTheDocument();
  });

  it('explains an empty scaffold and lists call changes', async () => {
    renderPage();
    expect(
      await screen.findByText(/No set-up while the intraday call is HOLD/)
    ).toBeInTheDocument();
    expect(await screen.findByText('today, intraday')).toBeInTheDocument();
    expect(screen.getByText('31%')).toBeInTheDocument();
  });

  it('links questions to Hella with the instrument and the question', async () => {
    renderPage();
    const link = await screen.findByRole('link', { name: /Why is NIFTY HOLD on the intraday/ });
    const href = new URL(link.getAttribute('href') ?? '', 'http://x');
    expect(href.pathname).toBe('/ai-console/agent');
    expect(href.searchParams.get('symbol')).toBe('NIFTY');
    expect(href.searchParams.get('q')).toMatch(/^Why is NIFTY HOLD/);
  });

  it('moves between horizons with the arrow keys', async () => {
    const user = userEvent.setup();
    renderPage();
    const strip = await screen.findByRole('tablist', { name: 'Signal horizon' });
    const [first] = within(strip).getAllByRole('tab');
    first!.focus();
    await user.keyboard('{ArrowRight}');
    expect(screen.getByRole('tab', { name: /End of day/ })).toHaveAttribute(
      'aria-selected',
      'true'
    );
  });
});
