import { describe, expect, it } from 'vitest';
import type { SessionBandRow, WireNumber } from '../../app/lib/contexts/global-markets/types';
import {
  byRegion,
  fmtLevel,
  fmtPercent,
  intoLanes,
  sparkPath,
  tone
} from '../../app/routes/terminal/global-index-analysis/gia-data';

/**
 * GIA's client-side shaping.
 *
 * The lane packer is the one with real consequences: Europe and the US overlap
 * by two hours and Asia opens while the US is still settling, so a packer that
 * let two bands share a lane would draw them on top of each other and the
 * timeline would read as a shorter night than it was.
 */
function band(key: string, start: number, end: number): SessionBandRow {
  return {
    key,
    label: key,
    region: 'americas',
    opens_at: '2026-09-23T19:00:00+05:30',
    closes_at: '2026-09-24T01:30:00+05:30',
    state: 'closed',
    start_fraction: start,
    end_fraction: end,
    change_percent: '-0.75'
  };
}

describe('intoLanes', () => {
  it('keeps overlapping sessions in separate lanes', () => {
    const lanes = intoLanes([band('EU', 0, 0.5), band('US', 0.3, 0.9)]);

    expect(lanes).toHaveLength(2);
  });

  it('reuses a lane once the previous session has closed', () => {
    const lanes = intoLanes([band('EU', 0, 0.3), band('US', 0.4, 0.9)]);

    expect(lanes).toHaveLength(1);
    expect(lanes[0]?.map((b) => b.key)).toEqual(['EU', 'US']);
  });

  it('packs every band exactly once', () => {
    const bands = [band('A', 0, 0.4), band('B', 0.2, 0.6), band('C', 0.5, 1), band('D', 0, 1)];

    const packed = intoLanes(bands).flat();

    expect(packed).toHaveLength(bands.length);
    expect(new Set(packed.map((b) => b.key)).size).toBe(bands.length);
  });

  it('orders lanes by when the baton arrives', () => {
    const lanes = intoLanes([band('LATE', 0.8, 1), band('EARLY', 0, 0.2)]);

    expect(lanes[0]?.[0]?.key).toBe('EARLY');
  });
});

describe('sparkPath', () => {
  it('draws a path through the series', () => {
    const path = sparkPath(['100', '110', '105']);

    expect(path.startsWith('M0.00,')).toBe(true);
    expect(path.split('L')).toHaveLength(3);
  });

  it('draws nothing for a series too short to have a shape', () => {
    expect(sparkPath([])).toBe('');
    expect(sparkPath(['100'])).toBe('');
  });

  it('skips the nulls a provider leaves for holidays', () => {
    // A holiday arrives as null; plotting it as zero would draw a cliff to the
    // axis that never happened.
    const path = sparkPath(['100', null as unknown as WireNumber, '110']);

    expect(path.split('L')).toHaveLength(2);
  });

  it('draws a flat series down the middle rather than dividing by zero', () => {
    const path = sparkPath(['100', '100', '100']);

    expect(path).toContain('50.00');
    expect(path).not.toContain('NaN');
  });
});

describe('formatting', () => {
  it('signs a percentage with a true minus', () => {
    expect(fmtPercent('-0.755')).toBe('−0.76%');
    expect(fmtPercent('1.33')).toBe('+1.33%');
  });

  it('renders a missing figure as a dash, never as zero', () => {
    // The rule the whole context is built on: null means "not known".
    expect(fmtPercent(null)).toBe('—');
    expect(fmtLevel(null)).toBe('—');
  });

  it('has no tone for an unknown or unchanged value', () => {
    expect(tone(null)).toBeNull();
    expect(tone('0')).toBeNull();
    expect(tone('-0.1')).toBe('down');
    expect(tone('0.1')).toBe('up');
  });
});

describe('byRegion', () => {
  it('groups in handoff order and drops regions with no rows', () => {
    const rows = [
      { region: 'americas', key: 'SPX' },
      { region: 'asia', key: 'NIKKEI' }
    ] as Parameters<typeof byRegion>[0];

    const groups = byRegion(rows);

    expect(groups.map((g) => g.region)).toEqual(['asia', 'americas']);
  });
});
