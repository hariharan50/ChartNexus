import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { GlobalView } from '../../app/lib/contexts/global-markets/types';
import {
  countdownLabel,
  gapForecast,
  inPreOpenWatch,
  minutesToOpen
} from '../../app/lib/contexts/market-data/gap-forecast';

/**
 * The pre-open gap forecast.
 *
 * What this replaces: before the bell a broker's `open_price` is the *previous*
 * session's, so the old card subtracted it from the previous close and
 * published the result as today's verdict — a confident FLAT, at 08:00, about a
 * session that had not happened. The backend now sends no gap in that window
 * and this derivation fills it from GIFT NIFTY, which actually trades overnight
 * and actually settles to NIFTY.
 *
 * So the assertions are about two things: that the number comes off the
 * contract rather than off anything inferred, and that the forecast declines to
 * exist whenever it would have to be invented.
 */
function view(overrides: Partial<GlobalView> = {}): GlobalView {
  return {
    as_of: '2026-09-28T02:30:00Z',
    window: {
      opened_at: '2026-09-25T10:00:00Z',
      closes_at: '2026-09-28T03:45:00Z',
      target_session: '2026-09-28',
      progress: 0.82
    },
    markets: [],
    regions: [],
    bands: [],
    pressure: { score: '41.20', band: 'up', contributions: [], missing: [] },
    implied: {
      gift_level: '23407.63',
      gift_change: '38.10',
      gift_change_percent: '0.16',
      nifty_spot: '23265.33',
      reference_close: '23265.33',
      nifty_is_trading: false,
      basis: '142.30',
      implied_level: '23407.63',
      gap_points: '142.30',
      gap_percent: '0.61',
      signal: 'gap_up'
    },
    gift: null,
    verdict: 'agree',
    source: 'live',
    gift_source: 'live',
    region_labels: {},
    ...overrides
  };
}

describe('gapForecast', () => {
  it('reads the expected gap straight off the contract', () => {
    const forecast = gapForecast(view(), 'NIFTY 50');

    expect(forecast).toBeDefined();
    expect(forecast?.signal).toBe('gap_up');
    expect(forecast?.points).toBe(142.3);
    expect(forecast?.percent).toBe(0.61);
    expect(forecast?.impliedLevel).toBe(23407.63);
    expect(forecast?.referenceClose).toBe(23265.33);
  });

  it('carries the bell it is forecasting, as the server placed it', () => {
    // Off the server's own window rather than reconstructed from a date here:
    // two places computing "the next Indian open" is two places to get a
    // holiday wrong.
    expect(gapForecast(view(), 'NIFTY 50')?.opensAt).toEqual(new Date('2026-09-28T03:45:00Z'));
  });

  it('does not exist without a contract quote', () => {
    // The composite alone is an inference about an inference. Putting a points
    // figure on screen that no instrument is quoting is the thing this whole
    // module exists to stop.
    expect(gapForecast(view({ implied: null }), 'NIFTY 50')).toBeUndefined();
  });

  it('does not exist without a response at all', () => {
    expect(gapForecast(undefined, 'NIFTY 50')).toBeUndefined();
  });

  it('rejects a pair that cannot be true', () => {
    const broken = view();
    const forecast = gapForecast(
      view({ implied: { ...broken.implied!, reference_close: '0' } }),
      'NIFTY 50'
    );

    expect(forecast).toBeUndefined();
  });

  describe('confidence', () => {
    it('is high when both reads agree and the whole world was priced', () => {
      expect(gapForecast(view(), 'NIFTY 50')?.confidence).toBe('high');
    });

    it('is low whenever the contract itself is simulated', () => {
      // Overriding everything else in its favour: a synthetic GIFT is not a
      // forecast at all, however well the rest of the page is doing.
      const forecast = gapForecast(view({ gift_source: 'mock' }), 'NIFTY 50');

      expect(forecast?.confidence).toBe('low');
      expect(forecast?.confidenceReason).toMatch(/NSE IX could not be reached/);
    });

    it('is low when most of the cross-check is missing', () => {
      const thin = view({
        pressure: {
          score: '12.00',
          band: 'flat',
          contributions: [],
          missing: ['sp500', 'dax', 'n225']
        }
      });

      expect(gapForecast(thin, 'NIFTY 50')?.confidence).toBe('low');
    });

    it('steps down to medium when the two reads disagree, and says so', () => {
      const split = gapForecast(view({ verdict: 'disagree' }), 'NIFTY 50');

      expect(split?.confidence).toBe('medium');
      expect(split?.confidenceReason).toMatch(/disagree/);
    });
  });
});

describe('the pre-open watch window', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('opens at 08:00 IST and closes at the bell', () => {
    // 02:29Z is 07:59 IST on a Monday; 02:30Z is 08:00.
    vi.setSystemTime(new Date('2026-09-28T02:29:00Z'));
    expect(inPreOpenWatch()).toBe(false);

    vi.setSystemTime(new Date('2026-09-28T02:30:00Z'));
    expect(inPreOpenWatch()).toBe(true);

    // 03:44Z is 09:14 IST — the last minute before the open.
    vi.setSystemTime(new Date('2026-09-28T03:44:00Z'));
    expect(inPreOpenWatch()).toBe(true);

    vi.setSystemTime(new Date('2026-09-28T03:45:00Z'));
    expect(inPreOpenWatch()).toBe(false);
  });

  it('is shut at the weekend, whatever the clock says', () => {
    // Saturday 08:30 IST. Nothing opens, so nothing is being counted down to.
    vi.setSystemTime(new Date('2026-10-03T03:00:00Z'));

    expect(inPreOpenWatch()).toBe(false);
  });

  it('counts the minutes left to 09:15', () => {
    vi.setSystemTime(new Date('2026-09-28T02:30:00Z'));

    expect(minutesToOpen()).toBe(75);
    expect(countdownLabel(75)).toBe('1h 15m');
  });

  it('reads under the hour without an empty hours figure', () => {
    expect(countdownLabel(14)).toBe('14m');
    expect(countdownLabel(0)).toBe('now');
    expect(countdownLabel(-3)).toBe('now');
  });
});
