import { describe, expect, it } from 'vitest';
import {
  clockLabel,
  dateLabel,
  freshnessLabel,
  REFETCH_MS,
  STALE_AFTER_MS
} from '../../app/routes/terminal/options/open-interest/oi-data';

/**
 * The header freshness readout.
 *
 * It exists because a page that polls faithfully and receives identical bytes
 * looks exactly like a page that has stopped polling. This is the only thing on
 * screen that tells a quiet feed from a dead one, so its boundaries are worth
 * pinning down.
 */

const NOW = Date.parse('2026-08-06T07:09:26Z'); // 12:39:26 IST

describe('freshnessLabel', () => {
  it('reads as immediate for the first few seconds', () => {
    expect(freshnessLabel(NOW, NOW)).toBe('just now');
    expect(freshnessLabel(NOW - 4_000, NOW)).toBe('just now');
  });

  it('counts seconds up to a minute', () => {
    expect(freshnessLabel(NOW - 5_000, NOW)).toBe('5s ago');
    expect(freshnessLabel(NOW - 15_000, NOW)).toBe('15s ago');
    expect(freshnessLabel(NOW - 59_000, NOW)).toBe('59s ago');
  });

  it('rolls over to minutes and then hours', () => {
    expect(freshnessLabel(NOW - 60_000, NOW)).toBe('1m ago');
    expect(freshnessLabel(NOW - 59 * 60_000, NOW)).toBe('59m ago');
    expect(freshnessLabel(NOW - 60 * 60_000, NOW)).toBe('1h ago');
    expect(freshnessLabel(NOW - 5 * 60 * 60_000, NOW)).toBe('5h ago');
  });

  it('says so when nothing has ever arrived', () => {
    // `dataUpdatedAt` is 0 before the first successful fetch. Rendering that as
    // a 56-year-old timestamp would be worse than useless.
    expect(freshnessLabel(0, NOW)).toBe('never');
  });

  it('never reports the future', () => {
    // Clock skew between the browser and the response should not produce
    // "-3s ago".
    expect(freshnessLabel(NOW + 5_000, NOW)).toBe('just now');
  });
});

describe('staleness threshold', () => {
  it('allows a couple of missed polls before crying wolf', () => {
    // One dropped request is normal; three means something is wrong.
    expect(STALE_AFTER_MS).toBe(REFETCH_MS * 3);
    expect(STALE_AFTER_MS).toBeGreaterThan(REFETCH_MS * 2);
  });
});

describe('header labels', () => {
  it('renders the IST trading date, not the viewer’s', () => {
    // 19:00 UTC is already the next day in IST. A trader in London must still
    // see the Indian session date.
    expect(dateLabel(Date.parse('2026-08-06T19:00:00Z'))).toBe('7 Aug');
    expect(dateLabel(NOW)).toBe('6 Aug');
  });

  it('renders a ticking IST clock with seconds', () => {
    expect(clockLabel(NOW)).toBe('12:39:26 pm');
  });
});
