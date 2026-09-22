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
  surface: '#111524',
  tooltipBg: '#111524',
  tooltipText: '#e6e9f2',
  call: '#22c55e',
  put: '#ef4444',
  marker: '#f59e0b',
  atmBand: '#1b2030',
  onMarker: '#ffffff',
  spotLabelBg: '#1b2030',
  spotLabelText: '#e6e9f2',
  maxPainLabelBg: '#3b2a12',
  // The eight categorical slots. Distinct placeholder values rather than
  // real palette colours: these fixtures assert that a builder reaches for
  // the right *role*, and a recognisable hex would let a wrong lookup pass.
  series1: '#111111',
  series2: '#222222',
  series3: '#333333',
  series4: '#444444',
  series5: '#555555',
  series6: '#666666',
  series7: '#777777',
  series8: '#888888'
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

  it('keeps late-session captures apart instead of piling them on the close', () => {
    // The tooltip is axis-triggered, so every series value sharing the hovered
    // x is listed. This axis used to clamp at minute 375 (15:30), which put
    // every capture after the F&O close moved to 15:40 on the same position —
    // ten minutes of one-minute snapshots stacked into one hover, and a tooltip
    // that ran off the screen.
    const late = ['2026-08-07T09:55:00Z', '2026-08-07T10:00:00Z', '2026-08-07T10:05:00Z'];
    const series = (
      build({
        timestamps: late, // 15:25, 15:30 and 15:35 IST
        futures: [24_600, 24_610, 24_620],
        lines: [{ id: '24600CE', label: '24600 CE', color: '#ec4899', values: [10, 20, 30] }]
      }).series as Series[]
    ).find((s) => s.id === '24600CE');

    const xs = (series?.data as [number, number][]).map(([x]) => x);
    expect(xs).toEqual([370, 375, 380]);
    expect(new Set(xs).size).toBe(xs.length);
  });

  it('separates two captures inside the same minute', () => {
    // The x used to be floored to whole minutes, which collided any two
    // captures in the same minute — routine at a 60-second ingest cadence, and
    // another way to get two rows per contract in one tooltip.
    const series = (
      build({
        timestamps: ['2026-08-07T04:18:10Z', '2026-08-07T04:18:50Z'],
        futures: [24_680, 24_681],
        lines: [{ id: 'a', label: 'a', color: '#fff', values: [1, 2] }]
      }).series as Series[]
    ).find((s) => s.id === 'a');

    const xs = (series?.data as [number, number][]).map(([x]) => x);
    expect(new Set(xs).size).toBe(2);
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
