import { describe, expect, it } from 'vitest';
import {
  buildMultiSeriesOption,
  seriesColor,
  SERIES_PALETTE
} from '../../app/lib/shared/charts/options/multi-series';
import type { ChartTheme } from '../../app/lib/shared/charts/theme/types';

/**
 * The option object behind the Options Lab series charts.
 *
 * `buildMultiSeriesOption` is pure and returns plain data, which is the whole
 * reason it lives apart from the component — the axis decisions below are the
 * ones that silently drew a wrong picture, and none of them need a canvas to
 * check.
 */

const THEME: ChartTheme = {
  axis: '#8b93a7',
  accent: '#3b82f6',
  grid: '#232838',
  tooltipBg: '#111524',
  tooltipText: '#e6e9f2',
  call: '#22c55e',
  put: '#ef4444',
  marker: '#f59e0b',
  atmBand: '#1b2030',
  onMarker: '#ffffff',
  spotLabelBg: '#1b2030',
  spotLabelText: '#e6e9f2',
  maxPainLabelBg: '#3b2a12'
};

/** 09:15, 09:48 and 09:51 IST on 2026-08-07 — a late start, as really happens. */
const T = ['2026-08-07T03:45:00Z', '2026-08-07T04:18:00Z', '2026-08-07T04:21:00Z'];

function build(overrides: Partial<Parameters<typeof buildMultiSeriesOption>[0]> = {}) {
  return buildMultiSeriesOption(
    {
      timestamps: T,
      futures: [null, 24_681, 24_685],
      lines: [{ id: '24600PE', label: '24600 PE', color: '#ec4899', values: [850, 1800, 1860] }],
      formatValue: (value) => `${value}`,
      formatPrice: (value) => `${value}`,
      valueAxisName: 'Open interest',
      showFutures: true,
      ...overrides
    },
    THEME
  );
}

type Axis = { type: string; min?: number; max?: number };
type Series = { id?: string; data?: unknown[]; connectNulls?: boolean };

describe('the x axis', () => {
  it('measures trading minutes, so gaps within a session are proportional', () => {
    // The bug this replaced: a category axis fed formatted clock strings spaces
    // every point equally, so a 33-minute recording gap drew exactly as wide as
    // the 3-minute step beside it — a straight ramp the market never made.
    const series = (build().series as Series[]).find((s) => s.id === '24600PE');
    // 09:15, 09:48, 09:51 -> 0, 33 and 36 minutes past the bell.
    expect(series?.data).toEqual([
      [0, 850],
      [33, 1800],
      [36, 1860]
    ]);
  });

  it('leaves blank track past the newest reading', () => {
    // A live chart whose last point sits hard against the frame reads as though
    // it has stopped rather than as though it is still going.
    // The newest point sits at minute 36; the axis has to run past it.
    const axis = build().xAxis as Axis;
    expect(axis.max!).toBeGreaterThan(36);
  });

  it('gives a single point somewhere to sit', () => {
    // No span to take a percentage of; the axis must not collapse to min == max.
    const axis = build({
      timestamps: [T[0]!],
      futures: [24_600],
      lines: [{ id: 'x', label: 'x', color: '#fff', values: [1] }]
    }).xAxis as Axis;
    expect(axis.max!).toBeGreaterThan(axis.min!);
  });
});

describe('gaps in a line', () => {
  it('does not bridge a leg that was not yet listed', () => {
    // Connecting across leading nulls would draw the contract flat at its first
    // real value back to the bell, inventing a build that never happened.
    const series = (
      build({
        lines: [{ id: 'new', label: 'new', color: '#fff', values: [null, null, 900] }]
      }).series as Series[]
    ).find((s) => s.id === 'new');
    expect(series?.connectNulls).toBe(false);
  });

  it('does bridge the futures overlay, which merely went unrecorded', () => {
    // Nobody captured the index at 09:15; that is a hole in the recording, not
    // the future ceasing to trade.
    const futures = (build().series as Series[]).find((s) => s.id === 'futures');
    expect(futures?.connectNulls).toBe(true);
  });
});

describe('series colours', () => {
  it('wrap rather than running out', () => {
    expect(seriesColor(SERIES_PALETTE.length)).toBe(SERIES_PALETTE[0]);
  });

  it('follow position in the selection, so the sidebar chips act as one legend', () => {
    expect(seriesColor(0)).not.toBe(seriesColor(1));
  });
});
