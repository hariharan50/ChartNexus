import { render, screen } from '@testing-library/react';
import { createRoutesStub } from 'react-router';
import { describe, expect, it } from 'vitest';
import { retiredSlugTarget, TOOLS, toolBySlug } from '../../app/routes/terminal/tools/catalog';
import Tools from '../../app/routes/terminal/tools/route';

/**
 * The Tools landing is a grid of links, and the part worth pinning is that
 * every catalogue entry becomes one box that actually goes somewhere. The
 * tools themselves are placeholders (B1…B12) and will be replaced one at a
 * time; the grid, the slugs and the open path must survive that.
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
    expect(toolBySlug('b2')?.name).toBe('B2');
    expect(toolBySlug('nope')).toBeUndefined();
  });
});

describe('retired slugs', () => {
  it('points a built tool’s old placeholder slug at its real page', () => {
    // B1 became Option Greeks; an open tab on /tools/b1 must land on the tool,
    // not on a 404.
    expect(retiredSlugTarget('b1')).toBe('option-greeks');
    expect(retiredSlugTarget('b2')).toBeUndefined();
    expect(retiredSlugTarget(undefined)).toBeUndefined();
  });

  it('keeps every retired slug pointing at a tool that exists', () => {
    expect(toolBySlug('option-greeks')).toBeDefined();
  });
});
