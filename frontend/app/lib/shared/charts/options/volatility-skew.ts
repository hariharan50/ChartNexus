import type { EChartsCoreOption } from '../echarts-modules';
import type { ChartTheme } from '../theme/types';
import { withAlpha } from '../theme/tokens';
import { priceIndex } from './open-interest';

/**
 * The implied-volatility smile across the strike ladder, over the open interest
 * sitting on each side.
 *
 * Pure: takes already-derived rows and returns an ECharts option, like its
 * siblings in this folder. Which strike the curve turns at, and where the two
 * markers land, is testable without rendering.
 *
 * **Three value axes, and each earns its place.** IV runs 8–30 volatility
 * points; OI runs to crores; the call/put IV ratio sits within a hair of 1.
 * Any two of them sharing a scale flattens one into a straight line — the ratio
 * on the IV axis is a line at the bottom of the plot, and IV on the OI axis is
 * a line at the bottom of that. The third axis is drawn invisibly: it exists to
 * scale its series, not to be read, because a reader who wants the number reads
 * the tooltip.
 *
 * **The bars overlap rather than sit side by side.** Call and put OI at one
 * strike are two claims on the same price, not two categories, and the overlap
 * is the interesting part — where both sides are loaded up. Drawn side by side
 * they read as unrelated columns, and at fifty strikes each is two pixels wide.
 */

/** One strike's row. Structurally the `SkewBar` the Volatility Skew page derives. */
export interface SkewChartBar {
  strike: number;
  /** What the x axis says — the strike, or its offset from the money. */
  label: string;
  /** The out-of-the-money blend the curve draws; `null` where unquoted. */
  iv: number | null;
  callIv: number | null;
  putIv: number | null;
  callOi: number;
  putOi: number;
  /** Call IV ÷ put IV; `null` unless both sides were quoted. */
  ratio: number | null;
}

/** A prior session's curve, drawn behind the live one. */
export interface SkewOverlay {
  id: string;
  label: string;
  /** Aligned to `bars`, `null` where that session had no such strike. */
  values: (number | null)[];
}

export interface VolatilitySkewInput {
  bars: SkewChartBar[];
  spot: number;
  /** Strike of the lowest point on the curve, or `null` to draw no marker. */
  lowestIv: number | null;
  showIv: boolean;
  showCallOi: boolean;
  showPutOi: boolean;
  showRatio: boolean;
  /** Previous sessions' curves, dimmed. Empty when T-Days is 0. */
  overlays: SkewOverlay[];
  ivColor: string;
  callColor: string;
  putColor: string;
  /** Formats an OI magnitude for the right axis and the tooltip. */
  formatOi: (value: number) => string;
  /** Formats a volatility for the left axis and the tooltip. */
  formatIv: (value: number) => string;
}

/** How solid the OI bars are. Low enough that the overlap reads as a third tone. */
const BAR_ALPHA = 0.55;
/** Vertical spacing between the spot and lowest-IV chips, so they cannot collide. */
const CHIP_PITCH = 22;

export function buildVolatilitySkewOption(
  input: VolatilitySkewInput,
  theme: ChartTheme
): EChartsCoreOption {
  return {
    backgroundColor: 'transparent',
    grid: { left: 8, right: 8, top: 32, bottom: 8, containLabel: true },
    tooltip: tooltip(input, theme),
    xAxis: {
      type: 'category',
      data: input.bars.map((bar) => bar.label),
      axisLine: { lineStyle: { color: theme.grid } },
      axisTick: { show: false },
      axisLabel: { color: theme.axis, fontSize: 11, hideOverlap: true, margin: 10 }
    },
    yAxis: [ivAxis(input, theme), oiAxis(input, theme), ratioAxis()],
    series: series(input, theme)
  };
}

function ivAxis(input: VolatilitySkewInput, theme: ChartTheme) {
  return {
    type: 'value' as const,
    name: 'IV',
    nameTextStyle: { color: theme.axis, fontSize: 10 },
    // The curve rarely reaches zero, and anchoring the axis there flattens the
    // very shape the page exists to show.
    scale: true,
    splitLine: { lineStyle: { color: theme.grid, type: 'dashed' as const } },
    axisLabel: { color: theme.axis, fontSize: 11, formatter: input.formatIv }
  };
}

function oiAxis(input: VolatilitySkewInput, theme: ChartTheme) {
  return {
    type: 'value' as const,
    name: 'OI',
    nameTextStyle: { color: theme.axis, fontSize: 10 },
    // Only one grid of split lines, or the two axes draw a lattice nothing can
    // be read through.
    splitLine: { show: false },
    axisLabel: { color: theme.axis, fontSize: 11, formatter: input.formatOi }
  };
}

/**
 * Scale-only, deliberately invisible.
 *
 * A ratio hovering around 1.0 needs its own range or it is a flat line; but a
 * third set of numbers down the side of an already two-axis chart is clutter
 * for a series that is off by default. The dashed line at parity is the
 * reference the reader actually needs, and the tooltip carries the number.
 */
function ratioAxis() {
  return { type: 'value' as const, show: false, scale: true };
}

function series(input: VolatilitySkewInput, theme: ChartTheme) {
  const { bars, showIv, showCallOi, showPutOi, showRatio } = input;
  const out: Record<string, unknown>[] = [];

  // Bars first so the curve draws over them.
  if (showCallOi)
    out.push(
      oiBar(
        'Call OI',
        bars.map((bar) => bar.callOi),
        input.callColor
      )
    );
  if (showPutOi)
    out.push(
      oiBar(
        'Put OI',
        bars.map((bar) => bar.putOi),
        input.putColor
      )
    );

  for (const overlay of input.overlays) {
    out.push({
      name: overlay.label,
      type: 'line',
      data: overlay.values,
      yAxisIndex: 0,
      smooth: true,
      symbol: 'none',
      // Thin and faint: prior sessions are context for today's shape, not
      // competitors to it.
      lineStyle: { color: withAlpha(theme.axis, 0.55), width: 1, type: 'dashed' as const },
      emphasis: { disabled: true },
      z: 3
    });
  }

  if (showIv) {
    out.push({
      name: 'IV',
      type: 'line',
      data: bars.map((bar) => bar.iv),
      yAxisIndex: 0,
      smooth: true,
      symbol: 'none',
      // A strike nobody quoted breaks the curve rather than being bridged: the
      // gap is the information.
      connectNulls: false,
      lineStyle: { color: input.ivColor, width: 2.5 },
      itemStyle: { color: input.ivColor },
      z: 5
    });
  }

  if (showRatio) {
    out.push({
      name: 'Vol Ratio',
      type: 'line',
      data: bars.map((bar) => bar.ratio),
      yAxisIndex: 2,
      smooth: true,
      symbol: 'none',
      connectNulls: false,
      lineStyle: { color: theme.marker, width: 1.5, type: 'dotted' as const },
      itemStyle: { color: theme.marker },
      markLine: parityLine(theme),
      z: 4
    });
  }

  // The markers hang off whichever series is first, so they survive any one
  // toggle being switched off. With everything off there is nothing to draw
  // them on — and nothing to draw them against.
  const host = out[0];
  if (host) host['markLine'] = markers(input, theme);

  return out;
}

function oiBar(name: string, data: number[], color: string) {
  return {
    name,
    type: 'bar',
    data,
    yAxisIndex: 1,
    barMaxWidth: 18,
    barCategoryGap: '20%',
    // Both sides occupy the same slot; the translucency is what separates them.
    barGap: '-100%',
    itemStyle: { color: withAlpha(color, BAR_ALPHA), borderRadius: [2, 2, 0, 0] },
    z: 2
  };
}

/** Parity on the ratio's own hidden scale — where calls and puts are priced alike. */
function parityLine(theme: ChartTheme) {
  return {
    silent: true,
    symbol: 'none',
    data: [
      {
        yAxis: 1,
        lineStyle: { color: withAlpha(theme.marker, 0.5), type: 'dashed' as const, width: 1 },
        label: {
          show: true,
          position: 'insideEndTop' as const,
          formatter: 'Parity',
          color: theme.axis,
          fontSize: 10
        }
      }
    ]
  };
}

/**
 * Spot, and the trough of the curve.
 *
 * Spot keeps the treatment it has on Open Interest, Max Pain and Gamma Exposure
 * — dotted, on a raised-surface chip — so a reader moving between the pages
 * sees the same marker mean the same thing. It is placed by fractional index so
 * it lands *between* strike columns where it belongs, rather than snapping onto
 * the nearest one and misreporting where the market is.
 */
function markers(input: VolatilitySkewInput, theme: ChartTheme) {
  const { bars, spot, lowestIv } = input;
  const strikes = bars.map((bar) => bar.strike);
  const lines: Record<string, unknown>[] = [];

  if (strikes.length === 0) return { silent: true, symbol: 'none', data: lines };

  if (Number.isFinite(spot) && spot > 0) {
    lines.push({
      xAxis: priceIndex(strikes, spot),
      lineStyle: { color: theme.axis, type: 'dotted', width: 1.5 },
      label: {
        show: true,
        position: 'end',
        distance: 0,
        formatter: `Spot: ${spot.toFixed(1)}`,
        color: theme.spotLabelText,
        backgroundColor: theme.spotLabelBg,
        padding: [3, 6],
        borderRadius: 4,
        fontSize: 11
      }
    });
  }

  if (lowestIv !== null) {
    lines.push({
      xAxis: priceIndex(strikes, lowestIv),
      lineStyle: { color: theme.accent, type: 'dashed', width: 1.5 },
      label: {
        show: true,
        position: 'end',
        // The one thing keeping this chip off spot's on a quiet day, when the
        // trough sits within a strike or two of the money.
        distance: CHIP_PITCH,
        formatter: `Lowest IV: ${Math.round(lowestIv)}`,
        color: theme.accent,
        backgroundColor: theme.spotLabelBg,
        borderColor: theme.accent,
        borderWidth: 1,
        padding: [3, 6],
        borderRadius: 4,
        fontSize: 11
      }
    });
  }

  return { silent: true, symbol: 'none', data: lines };
}

/**
 * The full readout, unlike Gamma Exposure's bare axis pointer.
 *
 * There, one number per strike made a floating box pure obstruction. Here a
 * strike carries five — two volatilities, two open interests and their ratio —
 * and no amount of axis labelling gets those to the reader.
 */
function tooltip(input: VolatilitySkewInput, theme: ChartTheme) {
  return {
    trigger: 'axis' as const,
    axisPointer: { type: 'shadow' as const },
    backgroundColor: theme.tooltipBg,
    borderWidth: 0,
    textStyle: { color: theme.tooltipText, fontSize: 12 },
    formatter: (params: unknown) => {
      const list = Array.isArray(params) ? params : [params];
      const first = list[0] as { dataIndex?: number } | undefined;
      const index = first?.dataIndex;
      if (index === undefined) return '';
      const bar = input.bars[index];
      if (!bar) return '';
      return tooltipHtml(input, bar);
    }
  };
}

export function tooltipHtml(input: VolatilitySkewInput, bar: SkewChartBar): string {
  const rows: string[] = [];
  const iv = (value: number | null) => (value === null ? '—' : input.formatIv(value));

  if (input.showIv) rows.push(row(input.ivColor, 'IV', iv(bar.iv)));
  rows.push(row(input.callColor, 'Call IV', iv(bar.callIv)));
  rows.push(row(input.putColor, 'Put IV', iv(bar.putIv)));
  if (input.showCallOi) rows.push(row(input.callColor, 'Call OI', input.formatOi(bar.callOi)));
  if (input.showPutOi) rows.push(row(input.putColor, 'Put OI', input.formatOi(bar.putOi)));
  if (input.showRatio) {
    rows.push(row('transparent', 'Vol Ratio', bar.ratio === null ? '—' : bar.ratio.toFixed(2)));
  }

  return `<div style="font-weight:700;margin-bottom:4px">${bar.strike}</div>${rows.join('')}`;
}

function row(color: string, name: string, value: string): string {
  const dot =
    color === 'transparent'
      ? '<span style="display:inline-block;width:8px"></span>'
      : `<span style="display:inline-block;width:8px;height:8px;border-radius:2px;background:${color}"></span>`;
  return (
    `<div style="display:flex;align-items:center;gap:6px;line-height:1.6">${dot}` +
    `<span style="flex:1">${name}</span><b>${value}</b></div>`
  );
}
