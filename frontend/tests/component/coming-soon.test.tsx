import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import ComingSoon from '../../app/lib/shared/ui/ComingSoon';

/**
 * The placeholder a dozen unbuilt pages share.
 *
 * The badge became overridable so PMS could say "Under development" without
 * rewording the rest, and the default is what the other pages depend on — a
 * shared component that changed every caller's wording by accident would be a
 * quiet, wide regression.
 */
describe('ComingSoon', () => {
  it('says "Coming soon" unless told otherwise', () => {
    render(<ComingSoon title="IV Grid" />);

    expect(screen.getByText('Coming soon')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'IV Grid' })).toBeInTheDocument();
  });

  it('takes a different state for the badge', () => {
    render(<ComingSoon title="PMS — Pre Market Screener" badge="Under development" />);

    expect(screen.getByText('Under development')).toBeInTheDocument();
    expect(screen.queryByText('Coming soon')).not.toBeInTheDocument();
  });

  it('omits the description when there is none to give', () => {
    const { container } = render(<ComingSoon title="IV Grid" />);

    expect(container.querySelector('p')).toBeNull();
  });
});
