import { act, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { SessionStatus } from '../../app/routes/terminal/future-lab/components/SessionHeader';

/**
 * The status strip that replaced the Future Lab's countdown ring.
 *
 * The fact it exists to carry is the **age of the data on screen**, and that
 * is the one a ring could never show: a ring keeps sweeping when a poll fails,
 * so a frozen board looked exactly like a live one. These pin that the age
 * climbs from when the payload landed, and that it turns red once the board is
 * genuinely behind rather than at the first missed beat.
 */

const NOW = new Date('2026-09-23T13:08:51Z'); // 18:38:51 IST

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(NOW);
});

afterEach(() => {
  vi.useRealTimers();
});

function strip() {
  return screen.getByText(/IST/).closest('span')!.parentElement!;
}

describe('SessionStatus', () => {
  it('shows the exchange clock, the cadence and the age', () => {
    render(<SessionStatus intervalSeconds={15} active updatedAt={NOW.getTime() - 5_000} />);

    expect(screen.getByText('23 Sep, 6:38:51 pm IST')).toBeInTheDocument();
    expect(screen.getByText('15s')).toBeInTheDocument();
    expect(screen.getByText('updated 5s ago')).toBeInTheDocument();
  });

  it('rolls a slow cadence into minutes', () => {
    /* The FII/DII pages poll every five minutes, and "300s" is a number the
       reader has to divide before it means anything. */
    render(<SessionStatus intervalSeconds={300} active updatedAt={NOW.getTime()} />);
    expect(screen.getByText('5m')).toBeInTheDocument();
  });

  it('says so plainly before anything has arrived', () => {
    /* Zero is not an age — it would read as "updated just now" on a board
       that has never loaded. */
    render(<SessionStatus intervalSeconds={15} active updatedAt={0} />);
    expect(screen.getByText('no data yet')).toBeInTheDocument();
  });

  it('counts the age up as the data sits there', () => {
    render(<SessionStatus intervalSeconds={15} active updatedAt={NOW.getTime()} />);
    expect(screen.getByText('updated 0s ago')).toBeInTheDocument();

    // Inside `act`, or React never flushes the state the interval set and the
    // strip keeps rendering the age it mounted with.
    act(() => {
      vi.advanceTimersByTime(7_000);
    });
    expect(screen.getByText('updated 7s ago')).toBeInTheDocument();
  });

  it('rolls the age into minutes rather than counting past sixty', () => {
    render(<SessionStatus intervalSeconds={15} active updatedAt={NOW.getTime() - 135_000} />);
    expect(screen.getByText('updated 2m ago')).toBeInTheDocument();
  });

  it('holds its nerve through a single missed beat', () => {
    /* One slow response is ordinary jitter. Colouring the strip for it would
       teach the reader to ignore the colour. */
    const { container } = render(
      <SessionStatus intervalSeconds={15} active updatedAt={NOW.getTime() - 20_000} />
    );
    expect(container.querySelector('[class*="stale"]')).toBeNull();
  });

  it('turns stale once the board is genuinely behind', () => {
    const { container } = render(
      <SessionStatus intervalSeconds={15} active updatedAt={NOW.getTime() - 40_000} />
    );
    expect(container.querySelector('[class*="stale"]')).not.toBeNull();
  });

  it('replaces the clock when the page is showing an archived day', () => {
    render(
      <SessionStatus
        intervalSeconds={15}
        active={false}
        updatedAt={NOW.getTime()}
        label="Archived · 2026-09-22"
      />
    );

    expect(screen.getByText('Archived · 2026-09-22')).toBeInTheDocument();
    expect(screen.queryByText(/IST/)).not.toBeInTheDocument();
  });

  it('says it is not refreshing when it is not', () => {
    render(<SessionStatus intervalSeconds={15} active={false} updatedAt={NOW.getTime()} />);
    expect(strip()).toHaveAttribute('title', 'Not refreshing');
  });
});
