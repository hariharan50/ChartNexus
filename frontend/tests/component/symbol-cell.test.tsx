import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import SymbolCell from '../../app/lib/shared/ui/SymbolCell';
import MANIFEST from '../../app/lib/shared/ui/logo-manifest.json';

/**
 * The ticker-plus-mark pairing every board identifies a row with.
 *
 * `SymbolAvatar` is tested on its own; what matters here is the contract the
 * four boards depend on — the ticker is the visible text, the company name is
 * only a hover label, and the class hooks a page passes survive, because two
 * of those boards still style the ticker through their own selectors.
 */

const WITH_LOGO = Object.keys(MANIFEST)[0]!;
const WITH_LOGO_EXT = (MANIFEST as Record<string, string>)[WITH_LOGO]!;

describe('SymbolCell', () => {
  it('shows the ticker as text with the company mark beside it', () => {
    const { container } = render(<SymbolCell symbol={WITH_LOGO} name="A Company Ltd" />);

    expect(container.textContent).toBe(WITH_LOGO);
    expect(container.querySelector('img')).toHaveAttribute(
      'src',
      `/logos/${WITH_LOGO}.${WITH_LOGO_EXT}`
    );
  });

  it('keeps the company name as a hover label, never as text', () => {
    /* The boards are dense enough that the name would cost a column. It is
       deliberately only in the title. */
    const { container } = render(<SymbolCell symbol="RELIANCE" name="Reliance Industries" />);

    expect(container.textContent).not.toContain('Reliance Industries');
    expect(container.firstElementChild).toHaveAttribute('title', 'Reliance Industries');
  });

  it('carries no title when there is no name, rather than an empty one', () => {
    const { container } = render(<SymbolCell symbol="RELIANCE" name={null} />);
    expect(container.firstElementChild).not.toHaveAttribute('title');
  });

  it('falls back to initials for a symbol with no committed mark', () => {
    const { container } = render(<SymbolCell symbol="NOSUCHTICKER" />);

    expect(container.querySelector('img')).toBeNull();
    expect(container.textContent).toBe('NONOSUCHTICKER');
  });

  it('keeps the class hooks a page passes for the wrapper and the ticker', () => {
    /* DivergingBoard styles the ticker through `.label .symbol`, and
       MoversTable owns the wrapper's column context. Dropping either prop
       would silently restyle those boards. */
    const { container } = render(
      <SymbolCell symbol="RELIANCE" className="page-wrap" tickerClassName="page-ticker" />
    );

    const wrapper = container.firstElementChild!;
    expect(wrapper.className).toContain('page-wrap');
    expect(wrapper.querySelector('.page-ticker')!.textContent).toBe('RELIANCE');
  });

  it('passes a size through to the mark', () => {
    const { container } = render(<SymbolCell symbol={WITH_LOGO} size={22} />);
    expect(container.querySelector('img')).toHaveAttribute('width', '22');
  });
});
