import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import RealtimeIndicator from '../../app/lib/shared/realtime/RealtimeIndicator';

/**
 * The live-stream dot in the terminal header.
 *
 * The distinction this component exists to keep is the one `DataSourceBadge`
 * already warns about: a connection indicator must not be read as a claim about
 * the numbers. A connected stream can be carrying simulated data, and a dropped
 * one leaves perfectly good cached prices on screen — so nothing here is red,
 * and every disconnected state says the pages are still updating on their timer.
 */
describe('RealtimeIndicator', () => {
  it('reads Live when connected', () => {
    render(<RealtimeIndicator state="open" />);

    expect(screen.getByText('Live')).toBeInTheDocument();
  });

  it.each([
    ['connecting', 'Connecting'],
    ['reconnecting', 'Reconnecting'],
    ['offline', 'Offline'],
    ['idle', 'Offline']
  ] as const)('reads %s as "%s"', (state, label) => {
    render(<RealtimeIndicator state={state} />);

    expect(screen.getByText(label)).toBeInTheDocument();
  });

  it('names the state for a screen reader, not just the colour', () => {
    render(<RealtimeIndicator state="reconnecting" />);

    expect(screen.getByRole('status')).toHaveAccessibleName('Live stream: Reconnecting');
  });

  it('says the pages still update when the stream is down', () => {
    // A reader must not think a dropped socket means the screen is frozen.
    render(<RealtimeIndicator state="offline" />);

    expect(screen.getByRole('status')).toHaveAttribute(
      'title',
      expect.stringContaining('updating on their timer')
    );
  });

  it('claims nothing about the numbers when connected', () => {
    // `DataSourceBadge` owns provenance; this must not imply "live prices".
    render(<RealtimeIndicator state="open" />);

    const title = screen.getByRole('status').getAttribute('title') ?? '';
    expect(title).not.toMatch(/\blive data\b|\breal\b|\bmarket price/i);
  });

  it('reports how long ago the last event arrived', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-10-09T08:31:00Z'));

    render(
      <RealtimeIndicator state="open" lastEventAt={new Date('2026-10-09T08:30:30Z').getTime()} />
    );

    expect(screen.getByRole('status')).toHaveAttribute(
      'title',
      expect.stringContaining('Last update 30s ago')
    );
  });

  it('omits the age when nothing has arrived yet', () => {
    render(<RealtimeIndicator state="connecting" />);

    expect(screen.getByRole('status').getAttribute('title')).not.toContain('Last update');
  });

  it('drops the word in compact mode but keeps the accessible name', () => {
    render(<RealtimeIndicator state="open" compact />);

    expect(screen.queryByText('Live')).not.toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveAccessibleName('Live stream: Live');
  });
});
