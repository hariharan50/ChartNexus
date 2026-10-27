import { describe, expect, it } from 'vitest';
import type { Provenance } from '$contexts/broker-connections/types';
import {
  alertable,
  classifyListed,
  countdownLabel,
  daysBetween,
  expiryDateLabel,
  leadMarker,
  monthlyFromRules,
  nextWeeklyFromRules,
  radarFor,
  urgencyFor
} from '$contexts/market-data/expiry-calendar';

const live = (): Provenance => ({
  source: 'live',
  fetched_at: '2026-10-27T13:36:51Z',
  age_seconds: 2,
  is_stale: false
});

const mock = (): Provenance => ({ ...live(), source: 'mock' });

describe('rule calendar', () => {
  // Tuesday 27 October 2026 is the anchor for most of these; the three indices
  // disagree about the week from here, which is the whole point of the table.
  it('gives NIFTY the Tuesday weekly', () => {
    // On a Tuesday, today is itself the expiry - not next week's.
    expect(nextWeeklyFromRules('NIFTY50', '2026-10-27')).toBe('2026-10-27');
    expect(nextWeeklyFromRules('NIFTY50', '2026-10-28')).toBe('2026-11-03');
  });

  it('gives SENSEX the Thursday weekly', () => {
    expect(nextWeeklyFromRules('SENSEX', '2026-10-27')).toBe('2026-10-29');
    expect(nextWeeklyFromRules('SENSEX', '2026-10-29')).toBe('2026-10-29');
  });

  it('gives BANK NIFTY no weekly at all', () => {
    expect(nextWeeklyFromRules('BANKNIFTY', '2026-10-27')).toBeUndefined();
  });

  it('puts the monthly on the last matching weekday', () => {
    // October 2026 ends on a Saturday, so the last Tuesday is the 27th and the
    // last Thursday the 29th.
    expect(monthlyFromRules('NIFTY50', '2026-10-01')).toBe('2026-10-27');
    expect(monthlyFromRules('SENSEX', '2026-10-01')).toBe('2026-10-29');
    expect(monthlyFromRules('BANKNIFTY', '2026-10-01')).toBe('2026-10-27');
  });

  it('rolls the monthly to the next month once it has passed', () => {
    // The 28th is past October's last Tuesday, so the answer must be
    // November's - never a date two days behind.
    expect(monthlyFromRules('NIFTY50', '2026-10-28')).toBe('2026-11-24');
  });

  it('crosses the year boundary', () => {
    expect(monthlyFromRules('NIFTY50', '2026-12-30')).toBe('2027-01-26');
  });
});

describe('classifying a broker list', () => {
  const today = '2026-10-27';

  it('calls the last date in a month the monthly', () => {
    const listed = [
      '2026-10-27',
      '2026-11-03',
      '2026-11-10',
      '2026-11-17',
      '2026-11-24',
      '2026-12-01'
    ];
    // The 27th is October's last listed date, and the list reaches into
    // December, so October's tail is demonstrably present.
    expect(classifyListed(listed, today)).toEqual({ weekly: '2026-11-03', monthly: '2026-10-27' });
  });

  it('refuses to name a monthly when the horizon truncated the month', () => {
    // Every entry sits inside October, so the last one is merely the last that
    // fitted inside the 42-day window - not necessarily the monthly.
    const listed = ['2026-10-27', '2026-10-29'];
    expect(classifyListed(listed, today)).toEqual({ weekly: '2026-10-27', monthly: undefined });
  });

  it('drops dates that have already settled', () => {
    const listed = ['2026-10-20', '2026-10-27', '2026-11-03', '2026-11-24', '2026-12-01'];
    expect(classifyListed(listed, today).weekly).toBe('2026-11-03');
  });

  it('ignores entries that are not ISO dates', () => {
    const listed = ['28-10-2026', '2026-11-03', '2026-11-24', '2026-12-01'];
    expect(classifyListed(listed, today).weekly).toBe('2026-11-03');
  });

  it('returns nothing from an empty or fully settled list', () => {
    expect(classifyListed([], today)).toEqual({});
    expect(classifyListed(['2026-10-01'], today)).toEqual({});
  });
});

describe('radarFor', () => {
  const today = '2026-10-27';

  it('prefers the broker list, holiday shifts included', () => {
    // A holiday has pushed the weekly from Tuesday the 3rd to Wednesday the
    // 4th. The published rule says Tuesday; the broker is right and wins.
    const listed = ['2026-10-27', '2026-11-04', '2026-11-10', '2026-11-24', '2026-12-01'];
    const radar = radarFor('NIFTY50', 'NIFTY 50', listed, live(), today);

    expect(radar.rows.map((row) => [row.kind, row.date])).toEqual([
      ['weekly', '2026-11-04'],
      ['monthly', '2026-10-27']
    ]);
    expect(radar.estimated).toBe(false);
  });

  it('falls back to the rules when the feed is the mock', () => {
    // The mock serves Thursdays for every instrument. Trusting it would print
    // NIFTY's weekly as Thursday - the exact error this arm exists to prevent.
    const listed = ['2026-10-29', '2026-11-05', '2026-11-12'];
    const radar = radarFor('NIFTY50', 'NIFTY 50', listed, mock(), today);

    expect(radar.rows[0]?.date).toBe('2026-10-27');
    expect(radar.estimated).toBe(true);
  });

  it('falls back to the rules before the query resolves', () => {
    // 29 October is October's last Thursday, so SENSEX's weekly and monthly
    // are the same date here and collapse to one `both` row.
    const radar = radarFor('SENSEX', 'SENSEX', undefined, undefined, today);
    expect(radar.rows).toEqual([
      { kind: 'both', date: '2026-10-29', daysAway: 2, urgency: 'near', estimated: true }
    ]);
    expect(radar.estimated).toBe(true);
  });

  it('keeps weekly and monthly apart once the month has rolled', () => {
    const radar = radarFor('SENSEX', 'SENSEX', undefined, undefined, '2026-10-30');
    expect(radar.rows.map((row) => [row.kind, row.date])).toEqual([
      ['weekly', '2026-11-05'],
      ['monthly', '2026-11-26']
    ]);
  });

  it('collapses one date carrying both meanings into a single row', () => {
    // 27 October is October's last Tuesday, so NIFTY's weekly and monthly are
    // the same contract date - one row, not the same date printed twice.
    const listed = ['2026-10-27', '2026-11-03', '2026-11-24', '2026-12-01'];
    const radar = radarFor('BANKNIFTY', 'BANK NIFTY', listed, live(), today);

    expect(radar.rows).toHaveLength(1);
    expect(radar.rows[0]?.kind).toBe('monthly');
  });

  it('marks BANK NIFTY as having no weekly series', () => {
    const radar = radarFor('BANKNIFTY', 'BANK NIFTY', undefined, undefined, today);
    expect(radar.weeklyRetired).toBe(true);
    expect(radar.rows.every((row) => row.kind === 'monthly')).toBe(true);
  });

  it('keeps a listed weekly while estimating only the truncated monthly', () => {
    // The list is believable about November's weeklies but stops before the
    // month's tail. Half the card is still real, and discarding it would throw
    // away a date the broker did publish.
    const listed = ['2026-11-03', '2026-11-10'];
    const radar = radarFor('NIFTY50', 'NIFTY 50', listed, live(), today);

    expect(radar.rows[0]).toMatchObject({ kind: 'weekly', date: '2026-11-03', estimated: false });
    expect(radar.rows[1]).toMatchObject({ kind: 'monthly', estimated: true });
  });

  it('never reports a negative countdown', () => {
    const radar = radarFor('NIFTY50', 'NIFTY 50', undefined, undefined, today);
    expect(radar.rows.every((row) => row.daysAway >= 0)).toBe(true);
  });
});

describe('urgency and labels', () => {
  it('tiers by days away', () => {
    expect(urgencyFor(0)).toBe('today');
    expect(urgencyFor(1)).toBe('tomorrow');
    expect(urgencyFor(3)).toBe('near');
    expect(urgencyFor(4)).toBe('distant');
  });

  it('counts calendar days across a month boundary', () => {
    expect(daysBetween('2026-10-27', '2026-11-03')).toBe(7);
    expect(daysBetween('2026-10-27', '2026-10-20')).toBe(-7);
  });

  it('formats a date the same way regardless of the viewer timezone', () => {
    // Parsed as UTC, not local: a viewer west of Greenwich parsing this as
    // local midnight would land a day earlier.
    expect(expiryDateLabel('2026-10-27')).toBe('Tue 27 Oct');
  });

  it('words the countdown', () => {
    expect(countdownLabel(0)).toBe('TODAY');
    expect(countdownLabel(1)).toBe('TOMORROW');
    expect(countdownLabel(9)).toBe('9 days');
  });
});

describe('alertable', () => {
  const today = '2026-10-27';
  const radars = [
    // Weekly today (it is a Tuesday), monthly the same day - one row.
    radarFor('NIFTY50', 'NIFTY 50', undefined, undefined, today),
    // Thursday weekly, two days out.
    radarFor('SENSEX', 'SENSEX', undefined, undefined, today),
    radarFor('BANKNIFTY', 'BANK NIFTY', undefined, undefined, today)
  ];

  it('returns only today and tomorrow, soonest first', () => {
    const hits = alertable(radars);
    expect(hits.every(({ marker }) => marker.daysAway <= 1)).toBe(true);
    expect(hits[0]?.radar.key).toBe('NIFTY50');
  });

  it('is empty when nothing is close', () => {
    const quiet = [radarFor('NIFTY50', 'NIFTY 50', undefined, undefined, '2026-10-29')];
    expect(alertable(quiet)).toEqual([]);
  });

  it('picks the soonest row as the lead', () => {
    const radar = radarFor('SENSEX', 'SENSEX', undefined, undefined, today);
    expect(leadMarker(radar)?.date).toBe('2026-10-29');
  });
});
