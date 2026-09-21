import type { EChartsCoreOption } from 'echarts/core';
import type { ChartTheme } from '../theme/types';

/**
 * The F&O board as a sector-grouped treemap.
 *
 * **Diverging, not sequential.** Price change has a meaningful zero, so the
 * scale runs from the bearish hue through a neutral grey to the bullish one.
 * The midpoint is grey on purpose — a hue there (the rainbow mistake) would
 * invent a third category at "unchanged".
 *
 * **Never colour alone.** Red and green are the classic colour-vision trap, and
 * they are also the convention every trading desk reads fluently. Both are
 * satisfied by always printing the number: each cell carries its ticker and its
 * signed percentage, so the colour is a fast index into information that is
 * also written down, never the only carrier of it.
 *
 * **Area is turnover, under a square root.** Raw turnover spans four orders of
 * magnitude across this universe, which would render most of the board as
 * slivers. The square root compresses that while keeping the ordering, so a
 * genuinely large name still reads as large and a small one stays clickable.
 */

export interface HeatmapCell {
  symbol: string;
  name: string | null;
  sector: string | null;
  changePercent: number | null;
  turnover: number;
  /** Everything below is for the hover card only — never for the geometry. */
  price?: string | number | null;
  oiChangePercent?: number | null;
  openInterest?: number | null;
  volume?: number | null;
  sentiment?: string | null;
}

/** How a cell's area is decided. */
export type HeatmapSize = 'turnover' | 'volume' | 'openInterest' | 'equal';

export interface HeatmapOptions {
  /**
   * Flat is the trading-desk reading: one grid, biggest top-left, so the eye
   * ranks by size immediately. Sector grouping answers a different question —
   * "where is the move concentrated" — and both are worth having.
   */
  layout?: 'flat' | 'sector';
  size?: HeatmapSize;
}

/**
 * The colour ramp.
 *
 * Tuned for contrast rather than for mathematical evenness, because the job is
 * "read the board across the room", not "estimate a value from a swatch".
 *
 * `MIN_TINT` is the important one: a contract down 0.1% is still *down*, and a
 * ramp that fades it to the background hides two thirds of a quiet session. So
 * any non-zero move starts at a clearly visible tint and grows from there.
 * Exactly zero — and an unmeasured change — stays neutral, which is the one
 * distinction the scale must not blur.
 *
 * Past `FULL_SCALE_PERCENT` the colour keeps deepening toward `DEEP_MIX`
 * instead of clipping, so a limit move still reads as more extreme than a 2%
 * one rather than landing on the same red.
 */
const FULL_SCALE_PERCENT = 2.5;
const MIN_TINT = 0.42;
/** Below 1 so the first fraction of a percent gains colour quickly. */
const TINT_EASE = 0.7;
/** How far the extremes darken past the pole colour. */
const DEEP_SCALE_PERCENT = 6;
const DEEP_MIX = 0.42;

const UNGROUPED = 'Other';

/** Cell labels are white in every theme: they sit on a saturated fill, not on
 *  the page, so they follow the mark rather than the page's ink. */
const LABEL_INK = '#ffffff';

export function buildFuturesHeatmapOption(
  cells: HeatmapCell[],
  theme: ChartTheme,
  { layout = 'flat', size = 'turnover' }: HeatmapOptions = {}
): EChartsCoreOption {
  const bullish = parseRgb(theme.call);
  const bearish = parseRgb(theme.put);
  // Flat sits just off the panel colour — near-invisible against the
  // background, which is what makes the coloured cells carry the whole board.
  const neutral = mix(parseRgb(theme.surface), parseRgb(theme.axis), 0.22);

  const poles = { bullish, bearish, neutral };
  const leaf = (cell: HeatmapCell) => ({
    name: cell.symbol,
    value: area(cell, size),
    itemStyle: { color: divergingColor(cell.changePercent, poles) },
    // Carried for the hover card; ECharts passes the whole data object through.
    change: cell.changePercent,
    company: cell.name,
    sector: cell.sector,
    price: cell.price ?? null,
    oiChange: cell.oiChangePercent ?? null,
    sentiment: cell.sentiment ?? null
  });

  let children: unknown[];
  if (layout === 'sector') {
    const bySector = new Map<string, HeatmapCell[]>();
    for (const cell of cells) {
      const key = cell.sector ?? UNGROUPED;
      bySector.set(key, [...(bySector.get(key) ?? []), cell]);
    }
    children = [...bySector.entries()]
      .map(([sector, members]) => ({ name: sector, children: members.map(leaf) }))
      .sort((a, b) => a.name.localeCompare(b.name));
  } else {
    // Largest first, so the treemap lays the heavyweights into the top-left
    // corner where the eye starts.
    children = [...cells].sort((a, b) => area(b, size) - area(a, size)).map(leaf);
  }

  return {
    tooltip: {
      backgroundColor: theme.tooltipBg,
      borderWidth: 0,
      textStyle: { color: theme.tooltipText, fontSize: 12 },
      formatter: (params: unknown) => {
        const point = params as {
          name?: string;
          data?: {
            change?: number | null;
            company?: string | null;
            sector?: string | null;
            price?: string | number | null;
            oiChange?: number | null;
            sentiment?: string | null;
          };
          treePathInfo?: { name: string }[];
        };
        const path = point.treePathInfo ?? [];
        // Depth 1 is a sector node in the grouped layout: name it, but do not
        // pretend a group has a price.
        if (path.length === 2) return escape(point.name ?? '');

        const data = point.data ?? {};
        const rows: string[] = [];
        if (data.company) rows.push(row('', escape(data.company), theme.tooltipText, true));
        if (data.sector) rows.push(row('', escape(data.sector), theme.axis, true));
        rows.push(row('Price', fixed(data.price), theme.tooltipText));
        rows.push(row('Price Change %', percent(data.change), toneOf(data.change, theme)));
        rows.push(row('OI Change %', percent(data.oiChange), toneOf(data.oiChange, theme)));
        if (data.sentiment) {
          rows.push(row('Sentiment', escape(data.sentiment), toneOf(data.change, theme)));
        }
        return [
          `<strong style="font-size:13px">${escape(point.name ?? '')}</strong>`,
          ...rows
        ].join('');
      }
    },
    series: [
      {
        type: 'treemap',
        roam: false,
        // One level of drill-down is a surprise in a dashboard tile; the board
        // is meant to be read whole.
        nodeClick: false,
        breadcrumb: { show: false },
        animationDuration: 260,
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        // Text sits in ink tokens, not in the cell's own colour.
        // White on a saturated fill, with a shadow so the ticker stays readable
        // at both the lightest and the deepest end of the ramp. The number is
        // the second carrier of the value: colour says "down", the figure says
        // how far, so a red/green-blind reader loses nothing.
        label: {
          show: true,
          formatter: (params: unknown) => {
            const point = params as { name?: string; data?: { change?: number | null } };
            const change = point.data?.change;
            if (change === null || change === undefined) return point.name ?? '';
            const sign = change >= 0 ? '+' : '';
            return `{sym|${point.name ?? ''}}
{pct|${sign}${change.toFixed(2)}%}`;
          },
          rich: {
            sym: { fontSize: 11, fontWeight: 700, color: LABEL_INK, lineHeight: 14 },
            pct: { fontSize: 10, fontWeight: 600, color: LABEL_INK, lineHeight: 13 }
          },
          color: LABEL_INK,
          textShadowColor: 'rgba(0, 0, 0, 0.55)',
          textShadowBlur: 3,
          overflow: 'truncate'
        },
        upperLabel: {
          show: layout === 'sector',
          height: 20,
          color: theme.tooltipText,
          fontSize: 11,
          fontWeight: 700,
          padding: [0, 0, 0, 4],
          overflow: 'truncate'
        },
        itemStyle: {
          // A hairline in the surface colour, so adjacent cells read as
          // separate marks rather than one continuous wash.
          borderColor: theme.surface,
          borderWidth: 1,
          gapWidth: 1
        },
        // Only the grouped layout has two levels to style. Flat is one grid of
        // contracts, so a sector-sized gutter around every cell would eat the
        // board.
        levels:
          layout === 'sector'
            ? [
                {
                  // Wider gutters between sectors than between contracts, so
                  // the grouping reads without drawing boxes around it.
                  itemStyle: { borderColor: theme.surface, borderWidth: 4, gapWidth: 4 },
                  upperLabel: { show: true }
                },
                { itemStyle: { borderColor: theme.surface, borderWidth: 1, gapWidth: 1 } }
              ]
            : [{ itemStyle: { borderColor: theme.surface, borderWidth: 1, gapWidth: 1 } }],
        data: children
      }
    ]
  };
}

interface Poles {
  bullish: Rgb;
  bearish: Rgb;
  neutral: Rgb;
}

/** A change percentage to a colour on the diverging scale. */
function divergingColor(change: number | null, poles: Poles): string {
  if (change === null || change === undefined || change === 0) {
    return toCss(poles.neutral);
  }

  const magnitude = Math.abs(change);
  const pole = change > 0 ? poles.bullish : poles.bearish;

  // Neutral -> pole, floored so even a hairline move is legible.
  const reach = Math.min(magnitude / FULL_SCALE_PERCENT, 1) ** TINT_EASE;
  const tint = MIN_TINT + (1 - MIN_TINT) * reach;
  const colour = mix(poles.neutral, pole, tint);

  // Past the pole, keep deepening rather than clipping, so the biggest movers
  // still stand out from the merely large ones.
  if (magnitude <= FULL_SCALE_PERCENT) return toCss(colour);
  const overflow = Math.min(
    (magnitude - FULL_SCALE_PERCENT) / (DEEP_SCALE_PERCENT - FULL_SCALE_PERCENT),
    1
  );
  return toCss(mix(colour, BLACK, overflow * DEEP_MIX));
}

const BLACK: Rgb = { r: 0, g: 0, b: 0 };

/**
 * A cell's area.
 *
 * Under a square root, because the chosen metrics span four orders of magnitude
 * across this universe and a linear mapping renders most of the board as
 * slivers. The root compresses that while preserving the ordering, so a
 * genuinely large name still reads as large and a small one stays clickable.
 *
 * The floor matters: a contract that barely traded must still be a target the
 * pointer can land on, not a hairline.
 */
function area(cell: HeatmapCell, size: HeatmapSize): number {
  if (size === 'equal') return 1;
  const raw =
    size === 'volume'
      ? (cell.volume ?? 0)
      : size === 'openInterest'
        ? (cell.openInterest ?? 0)
        : cell.turnover;
  return Math.max(Math.sqrt(Math.max(raw, 0)), 1);
}

interface Rgb {
  r: number;
  g: number;
  b: number;
}

/**
 * The theme resolves its tokens to real `rgb()` strings before handing them
 * over, so this only has to understand that one shape — see the note in
 * `theme/tokens.ts` on why the probe exists.
 */
function parseRgb(value: string): Rgb {
  const match = /rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)/i.exec(value);
  if (!match) return { r: 128, g: 128, b: 128 };
  return { r: Number(match[1]), g: Number(match[2]), b: Number(match[3]) };
}

function mix(from: Rgb, to: Rgb, weight: number): Rgb {
  return {
    r: Math.round(from.r + (to.r - from.r) * weight),
    g: Math.round(from.g + (to.g - from.g) * weight),
    b: Math.round(from.b + (to.b - from.b) * weight)
  };
}

function toCss({ r, g, b }: Rgb): string {
  return `rgb(${r}, ${g}, ${b})`;
}

/** One label/value line of the hover card. */
function row(label: string, value: string, colour: string, quiet = false): string {
  const name = label
    ? `<span style="opacity:.75">${label}:</span>`
    : `<span style="opacity:${quiet ? 0.75 : 1}"></span>`;
  return (
    `<div style="display:flex;gap:10px;justify-content:space-between;margin-top:3px">` +
    `${name}<span style="color:${colour};font-weight:600">${value}</span></div>`
  );
}

function percent(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`;
}

function fixed(value: string | number | null | undefined): string {
  const n = typeof value === 'string' ? Number(value) : value;
  if (n === null || n === undefined || !Number.isFinite(n)) return '—';
  return n.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

/** Values wear the direction they describe; an unmeasured one stays neutral. */
function toneOf(value: number | null | undefined, theme: ChartTheme): string {
  if (value === null || value === undefined || value === 0) return theme.tooltipText;
  return value > 0 ? theme.call : theme.put;
}

/** Company names are exchange-supplied text going into a tooltip's HTML. */
function escape(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
