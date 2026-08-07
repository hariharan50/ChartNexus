import { describe, expect, it } from 'vitest';
import {
  feedAgeLabel,
  feedAgeMs,
  FEED_STALE_AFTER_MS,
  freshnessLabel
} from '../../app/routes/terminal/options/open-interest/oi-data';
import { isTradingWindow } from '../../app/lib/shared/formatting/ist-clock';

/**
 * The signal that says a live chart has stopped being live.
 *
 * This exists because a dead ingest worker was invisible: the endpoint kept
 * answering in milliseconds, the clock kept ticking, and the series had not
 * grown for an hour. Everything on screen said "live" and the data was stale.
 */

/** 2026-08-07 is a Friday. 12:00 IST is 06:30 UTC. */
const MIDDAY = Date.parse('2026-08-07T06:30:00Z');
const EVENING = Date.parse('2026-08-07T14:00:00Z'); // 19:30 IST
const SATURDAY = Date.parse('2026-08-08T06:30:00Z');

describe('isTradingWindow', () => {
  it('is open inside the session on a weekday', () => {
    expect(isTradingWindow(MIDDAY)).toBe(true);
  });

  it('is shut after the close', () => {
    expect(isTradingWindow(EVENING)).toBe(false);
  });

  it('is shut at the weekend', () => {
    expect(isTradingWindow(SATURDAY)).toBe(false);
  });

  it('is shut before the bell', () => {
    // 09:00 IST — pre-open, nothing is being captured yet.
    expect(isTradingWindow(Date.parse('2026-08-07T03:30:00Z'))).toBe(false);
  });
});

describe('feedAgeMs', () => {
  it('is null while the series is keeping up', () => {
    const oneMinuteAgo = new Date(MIDDAY - 60_000).toISOString();
    expect(feedAgeMs(oneMinuteAgo, MIDDAY)).toBeNull();
  });

  it('reports the lag once the series stops growing', () => {
    // The real failure: the worker died at 12:53 and the page still read 13:58.
    const stalled = new Date(MIDDAY - 65 * 60_000).toISOString();
    const age = feedAgeMs(stalled, MIDDAY);
    expect(age).not.toBeNull();
    expect(Math.round(age! / 60_000)).toBe(65);
  });

  it('stays quiet after the close, when the series is meant to stop', () => {
    // Four hours behind at 19:30 is the close, not a fault. Warning here every
    // evening is how a warning gets ignored on the morning it matters.
    const atClose = new Date(EVENING - 4 * 60 * 60_000).toISOString();
    expect(feedAgeMs(atClose, EVENING)).toBeNull();
  });

  it('is null when there is no series at all', () => {
    expect(feedAgeMs(undefined, MIDDAY)).toBeNull();
  });

  it('tolerates a couple of missed captures', () => {
    const twoMinutes = new Date(MIDDAY - 2 * 60_000).toISOString();
    expect(feedAgeMs(twoMinutes, MIDDAY)).toBeNull();
    expect(FEED_STALE_AFTER_MS).toBeGreaterThan(2 * 60_000);
  });
});

describe('feedAgeLabel', () => {
  it('reads in minutes under the hour', () => {
    expect(feedAgeLabel(65 * 60_000)).toBe('1h 5m behind');
    expect(feedAgeLabel(7 * 60_000)).toBe('7m behind');
  });
});

describe('the two freshness measures are not the same thing', () => {
  it('a fresh response can carry a stale series', () => {
    // The whole bug in one assertion. `freshnessLabel` times the HTTP response
    // and reads "just now"; the data inside it is an hour old.
    const respondedNow = MIDDAY - 1_000;
    const seriesEndedAnHourAgo = new Date(MIDDAY - 60 * 60_000).toISOString();

    expect(freshnessLabel(respondedNow, MIDDAY)).toBe('just now');
    expect(feedAgeMs(seriesEndedAnHourAgo, MIDDAY)).not.toBeNull();
  });
});
