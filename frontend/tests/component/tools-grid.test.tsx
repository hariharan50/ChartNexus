import { render, screen } from '@testing-library/react';
import { createRoutesStub } from 'react-router';
import { describe, expect, it } from 'vitest';
import { retiredSlugTarget, TOOLS, toolBySlug } from '../../app/routes/terminal/tools/catalog';
import Tools from '../../app/routes/terminal/tools/route';

/**
 * The Tools landing is a grid of links, and the part worth pinning is that
 * every catalogue entry becomes one box that actually goes somewhere — and
 * that nothing else does. The grid once padded itself to twelve with generated
 * placeholders; only built tools belong in it now.
 */
describe('Tools landing', () => {
  function renderGrid() {
    const Stub = createRoutesStub([{ path: '/tools', Component: Tools }]);
    render(<Stub initialEntries={['/tools']} />);
  }

  it('renders one box per catalogue entry, each linking to its own page', () => {
    renderGrid();

    const boxes = screen.getAllByRole('link');
    expect(boxes).toHaveLength(TOOLS.length);
    for (const tool of TOOLS) {
      expect(screen.getByText(`Click to open ${tool.name}`)).toBeInTheDocument();
    }
    expect(boxes[0]).toHaveAttribute('href', `/tools/${TOOLS[0]!.slug}`);
  });

  it('keeps the section heading and its strapline', () => {
    renderGrid();

    expect(screen.getByRole('heading', { name: 'Tools' })).toBeInTheDocument();
    expect(
      screen.getByText('Analytical tools for options trading and market analysis')
    ).toBeInTheDocument();
  });
});

describe('tool lookup', () => {
  it('resolves a known slug and refuses an unknown one', () => {
    expect(toolBySlug('option-greeks')?.name).toBe('Option Greeks');
    expect(toolBySlug('straddle-chart')?.name).toBe('Straddle Chart');
    expect(toolBySlug('straddle-pnl')?.name).toBe('Straddle PnL Simulator');
    expect(toolBySlug('nope')).toBeUndefined();
  });

  it('never lists one slug twice', () => {
    // The reserved slots used to start at a hardcoded `b3`, which only held
    // while exactly two tools were built. A third turned `b3` into both a real
    // tool and a placeholder, and the placeholder shadowed it in the grid.
    const slugs = TOOLS.map((tool) => tool.slug);
    expect(new Set(slugs).size).toBe(slugs.length);
  });

  it('lists no placeholder slots', () => {
    // The grid used to generate B4…B12 to fill twelve boxes, advertising nine
    // tools that did not exist. Every entry must now be a built tool.
    expect(TOOLS.filter((tool) => /^b\d+$/i.test(tool.slug))).toEqual([]);
    expect(TOOLS).toHaveLength(3);
  });
});

describe('retired slugs', () => {
  it('points a built tool’s old placeholder slug at its real page', () => {
    // B1 became Option Greeks; an open tab on /tools/b1 must land on the tool,
    // not on a 404.
    expect(retiredSlugTarget('b1')).toBe('option-greeks');
    expect(retiredSlugTarget('b2')).toBe('straddle-chart');
    expect(retiredSlugTarget('b3')).toBe('straddle-pnl');
    expect(retiredSlugTarget('b4')).toBeUndefined();
    expect(retiredSlugTarget(undefined)).toBeUndefined();
  });

  it('keeps every retired slug pointing at a tool that exists', () => {
    expect(toolBySlug('option-greeks')).toBeDefined();
    expect(toolBySlug('straddle-chart')).toBeDefined();
    expect(toolBySlug('straddle-pnl')).toBeDefined();
  });

  it('never retires a slug that is still a live box', () => {
    // A retired slug redirects. One that is also in the grid would send a
    // reader who clicked the box straight back out of it.
    for (const slug of ['b1', 'b2', 'b3']) {
      expect(toolBySlug(slug)).toBeUndefined();
    }
  });
});
