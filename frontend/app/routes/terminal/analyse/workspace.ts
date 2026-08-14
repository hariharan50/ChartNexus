/**
 * Shared vocabulary for the chart workspace: the per-cell configuration and the
 * grid layouts. Kept in its own module so the toolbar, the cell and the route can
 * all name these types without importing each other.
 */

import type { ChartType } from '$shared/charts/tv/LwChart';
import type { IndicatorId } from './indicators';
import type { Interval } from './analyse-data';

export type LayoutId = '1' | '2' | '4';

/** How many charts each layout shows, and its grid label. */
export const LAYOUTS: { id: LayoutId; label: string; cells: number }[] = [
  { id: '1', label: 'Single', cells: 1 },
  { id: '2', label: 'Two across', cells: 2 },
  { id: '4', label: 'Grid of four', cells: 4 }
];

export function cellsInLayout(layout: LayoutId): number {
  return LAYOUTS.find((entry) => entry.id === layout)?.cells ?? 1;
}

/** One chart in the workspace — everything that makes it show what it shows. */
export interface CellConfig {
  symbol: string;
  interval: Interval;
  chartType: ChartType;
  /** Active indicator ids (an array, not a Set, so config stays plain data). */
  indicators: IndicatorId[];
  /** Whether this cell is in replay mode. */
  replay: boolean;
}

export function defaultCell(symbol: string): CellConfig {
  return { symbol, interval: '5m', chartType: 'candle', indicators: [], replay: false };
}

/** Replay playback speeds, in bars per second. */
export const REPLAY_SPEEDS = [0.5, 1, 2, 4] as const;
export type ReplaySpeed = (typeof REPLAY_SPEEDS)[number];
