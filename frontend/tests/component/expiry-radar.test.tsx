import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { radarFor } from '../../app/lib/contexts/market-data/expiry-calendar';
import { useNotificationPreferencesStore } from '../../app/lib/shared/ui/notification-preferences-store';
import ExpiryAlert from '../../app/routes/terminal/advanced-dashboard/components/ExpiryAlert';
import ExpiryCard from '../../app/routes/terminal/advanced-dashboard/components/ExpiryCard';

/**
 * The Advanced Dashboard's expiry indicator.
 *
 * What these tests actually guard is that **the card never depends on colour**.
 * Red names the weekly and amber the monthly, which is useful and is also the
 * first thing to fail for a reader who cannot tell the two apart, on a
 * greyscale screen, or in a screenshot. So every assertion here reaches for
 * text or an accessible name — if the suite can read the card, so can a screen
 * reader.
 *
 * The second thing they guard is the honesty of an *estimated* date. A
 * settlement date computed from the published rule and a date the exchange
 * confirmed are not the same claim, and rendering them identically is the
 * failure this feature was arranged to avoid.
 *
 * Dates are passed explicitly rather than read from the clock: a suite keyed
 * to the real today would pass this week and fail next Tuesday.
 */

const TUESDAY = '2026-10-27';

// Holiday-shifted weekly on Wednesday the 4th, so a confirmed list and the
// Tuesday rule visibly disagree.
const LISTED = ['2026-10-27', '2026-11-04', '2026-11-10', '2026-11-24', '2026-12-01'];
const live = {
  source: 'live',
  fetched_at: '2026-10-27T04:00:00Z',
  age_seconds: 1,
  is_stale: false
} as const;

describe('ExpiryCard', () => {
  it('names each contract, its date and how far off it is, in text', () => {
    render(<ExpiryCard radar={radarFor('NIFTY50', 'NIFTY 50', LISTED, live, TUESDAY)} />);

    expect(screen.getByText('Weekly')).toBeInTheDocument();
    expect(screen.getByText('Wed 4 Nov')).toBeInTheDocument();
    expect(screen.getByText('Monthly')).toBeInTheDocument();
    expect(screen.getByText('Tue 27 Oct')).toBeInTheDocument();
    expect(screen.getByText('TODAY')).toBeInTheDocument();
  });

  it('reads the whole row as a sentence for assistive tech', () => {
    render(<ExpiryCard radar={radarFor('NIFTY50', 'NIFTY 50', LISTED, live, TUESDAY)} />);

    expect(screen.getByLabelText('NIFTY 50 monthly expiry today, Tue 27 Oct')).toBeInTheDocument();
    expect(
      screen.getByLabelText('NIFTY 50 weekly expiry in 8 days, Wed 4 Nov')
    ).toBeInTheDocument();
  });

  it('says BANK NIFTY has no weekly series rather than leaving a gap', () => {
    render(<ExpiryCard radar={radarFor('BANKNIFTY', 'BANK NIFTY', LISTED, live, '2026-10-28')} />);

    expect(screen.getByText(/no weekly series/i)).toBeInTheDocument();
    expect(screen.queryByText('Weekly')).not.toBeInTheDocument();
  });

  it('labels a date it computed rather than received', () => {
    // The mock provider serves Thursdays for every instrument, so the card
    // falls back to the published Tuesday rule - and has to say so.
    const mock = { ...live, source: 'mock' } as const;
    render(<ExpiryCard radar={radarFor('NIFTY50', 'NIFTY 50', ['2026-10-29'], mock, TUESDAY)} />);

    expect(screen.getByText(/scheduled date/i)).toBeInTheDocument();
    expect(screen.getByText('Tue 27 Oct')).toBeInTheDocument();
  });

  it('makes no such claim when the broker confirmed the dates', () => {
    render(<ExpiryCard radar={radarFor('NIFTY50', 'NIFTY 50', LISTED, live, TUESDAY)} />);
    expect(screen.queryByText(/scheduled date/i)).not.toBeInTheDocument();
  });

  it('shows one row, not a repeated date, when the weekly is the monthly', () => {
    render(<ExpiryCard radar={radarFor('NIFTY50', 'NIFTY 50', undefined, undefined, TUESDAY)} />);

    expect(screen.getByText('Weekly + Monthly')).toBeInTheDocument();
    expect(screen.getAllByText('Tue 27 Oct')).toHaveLength(1);
  });
});

describe('ExpiryAlert', () => {
  const today = [radarFor('NIFTY50', 'NIFTY 50', LISTED, live, TUESDAY)];

  beforeEach(() => {
    window.sessionStorage.clear();
    useNotificationPreferencesStore.setState({
      toggles: { ...useNotificationPreferencesStore.getState().toggles, marketSchedule: true }
    });
  });

  afterEach(() => {
    window.sessionStorage.clear();
  });

  it('interrupts on an expiry today', async () => {
    render(<ExpiryAlert radars={today} sessionDate={TUESDAY} />);

    expect(await screen.findByText('Expiry today')).toBeInTheDocument();
    expect(screen.getByText(/NIFTY 50/)).toBeInTheDocument();
  });

  it('stays quiet when the nearest expiry is days out', async () => {
    const quiet = [radarFor('NIFTY50', 'NIFTY 50', LISTED, live, '2026-10-30')];
    const { container } = render(<ExpiryAlert radars={quiet} sessionDate="2026-10-30" />);

    // The effect that reads the dismissal has to run before "nothing rendered"
    // means anything, so wait a tick rather than asserting synchronously.
    await Promise.resolve();
    expect(container).toBeEmptyDOMElement();
  });

  it('is suppressed by the market-schedule notification toggle', async () => {
    useNotificationPreferencesStore.setState({
      toggles: { ...useNotificationPreferencesStore.getState().toggles, marketSchedule: false }
    });
    const { container } = render(<ExpiryAlert radars={today} sessionDate={TUESDAY} />);

    await Promise.resolve();
    expect(container).toBeEmptyDOMElement();
  });

  it('stays dismissed for the rest of the session', async () => {
    const { unmount } = render(<ExpiryAlert radars={today} sessionDate={TUESDAY} />);
    await userEvent.click(await screen.findByRole('button', { name: /dismiss expiry alert/i }));
    expect(screen.queryByText('Expiry today')).not.toBeInTheDocument();

    unmount();
    render(<ExpiryAlert radars={today} sessionDate={TUESDAY} />);
    await Promise.resolve();
    expect(screen.queryByText('Expiry today')).not.toBeInTheDocument();
  });

  it('comes back the next day, because dismissal is keyed to the session date', async () => {
    const { unmount } = render(<ExpiryAlert radars={today} sessionDate={TUESDAY} />);
    await userEvent.click(await screen.findByRole('button', { name: /dismiss expiry alert/i }));
    unmount();

    // Wednesday: NIFTY's weekly is now Wednesday the 4th, a week out, but
    // SENSEX settles tomorrow. Yesterday's dismissal must not silence it.
    const tomorrow = [radarFor('SENSEX', 'SENSEX', undefined, undefined, '2026-10-28')];
    render(<ExpiryAlert radars={tomorrow} sessionDate="2026-10-28" />);

    expect(await screen.findByText('Expiry tomorrow')).toBeInTheDocument();
  });
});
