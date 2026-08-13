import type { EChartsCoreOption } from '../echarts-modules';
import type { ChartTheme } from '../theme/types';

/**
 * The per-strike pain profile behind the Max Pain tool.
 *
 * Pure: takes already-derived points and returns an ECharts option, like its
 * two siblings in this folder.
 *
 * `open-interest.ts` is deliberately not reused. It carries three display
 * modes, hatched increase/decrease styling and an ATM highlight band, none of
 * which apply to a pain profile — bending it to a second purpose would make
 * both harder to read. What *is* shared is the marker treatment below, so the
 * two pages' spot lines are the same object drawn twice rather than two
 * lookalikes that drift apart.
 *
 * The two sides sit side by side at each strike rather than overlapping. Pain
 * is not a stacked quantity — a call holder's loss is not a put holder's — and
 * the shape being read is where one side overtakes the other.
 */

export interface PainBar {
  strike: number;
  callPain: number;
  putPain: number;
}

export interface MaxPainInput {
  bars: PainBar[];
  /** Where the market is now. */
  spot: number;
  /** The level that hurts most holders — the whole point of the chart. */
  maxPain: number;
  formatPain: (value: number) => string;
  callColor: string;
  putColor: string;
}

export function buildMaxPainOption(input: MaxPainInput, theme: ChartTheme): EChartsCoreOption {
  const { bars, formatPain, callColor, putColor } = input;

  return {
    backgroundColor: 'transparent',
    grid: { left: 8, right: 24, top: 44, bottom: 8, containLabel: true },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      appendTo: 'body',
      backgroundColor: theme.tooltipBg,
      borderColor: theme.grid,
      textStyle: { color: theme.tooltipText, fontSize: 12 },
      padding: [8, 12],
      formatter: (params: unknown) => {
        const arr = params as Array<{ dataIndex: number }>;
        const bar = arr.length ? bars[arr[0]!.dataIndex] : undefined;
        if (!bar) return '';
        return `
          <div style="font-weight:700;margin-bottom:4px">Strike: ${bar.strike}</div>
          <div style="color:${callColor}">Call Pain: ${formatPain(bar.callPain)}</div>
          <div style="color:${putColor}">Put Pain: ${formatPain(bar.putPain)}</div>`;
      }
    },
    xAxis: {
      type: 'category',
      data: bars.map((bar) => String(bar.strike)),
      axisLine: { lineStyle: { color: theme.grid } },
      axisTick: { show: false },
      axisLabel: { color: theme.axis, fontSize: 11, hideOverlap: true, margin: 10 }
    },
    yAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: theme.grid, type: 'dashed' } },
      axisLabel: { color: theme.axis, fontSize: 11, formatter: formatPain }
    },
    series: [
      {
        name: 'Call Pain',
        type: 'bar',
        data: bars.map((bar) => bar.callPain),
        itemStyle: { color: callColor },
        z: 2,
        markLine: markers(input, theme)
      },
      {
        name: 'Put Pain',
        type: 'bar',
        data: bars.map((bar) => bar.putPain),
        itemStyle: { color: putColor },
        z: 1
      }
    ]
  };
}

/**
 * The two vertical references: where the market is, and where it hurts most.
 *
 * Styled from the same theme roles the Open Interest chart uses — a dotted spot
 * line on a raised-surface chip, max pain on the always-dark brand chip — so a
 * reader moving between the two pages sees the same markers mean the same
 * things.
 */
function markers(input: MaxPainInput, theme: ChartTheme) {
  const { bars, spot, maxPain } = input;
  const strikes = bars.map((bar) => bar.strike);
  const lines: Record<string, unknown>[] = [];

  if (Number.isFinite(spot) && spot > 0 && strikes.length > 0) {
    lines.push({
      xAxis: priceIndex(strikes, spot),
      lineStyle: { color: theme.axis, type: 'dotted', width: 1.5 },
      label: {
        show: true,
        // Top of the plot, not the foot of the line: at the foot the two chips
        // sit straight on top of the strike labels they are pointing at.
        position: 'end',
        // Dropped one chip-height below Max Pain's, which also anchors at the
        // top. When spot and max pain land a strike or two apart their two
        // top-anchored chips overlap and the wider one hides the other; the
        // offset stacks them instead. Harmless when they are far apart — the
        // spot chip simply sits slightly lower.
        offset: [0, 22],
        formatter: `Spot : ${Math.round(spot)}`,
        color: theme.spotLabelText,
        backgroundColor: theme.spotLabelBg,
        padding: [3, 6],
        borderRadius: 4,
        fontSize: 11
      }
    });
  }

  const mpIdx = strikes.indexOf(maxPain);
  if (mpIdx >= 0) {
    lines.push({
      xAxis: mpIdx,
      lineStyle: { color: theme.marker, type: 'dashed', width: 1.5 },
      label: {
        show: true,
        // Top of the plot, not the foot of the line: at the foot the two chips
        // sit straight on top of the strike labels they are pointing at.
        position: 'end',
        formatter: `Max Pain : ${maxPain}`,
        color: theme.onMarker,
        backgroundColor: theme.maxPainLabelBg,
        padding: [3, 6],
        borderRadius: 4,
        fontSize: 11
      }
    });
  }

  return { silent: true, symbol: 'none', data: lines };
}

/**
 * Fractional category index for a price, so the spot line can land between two
 * strike columns rather than snapping onto one.
 *
 * The same derivation `oi-data.priceIndex` makes for the Open Interest chart;
 * duplicated here rather than imported so this chart module stays free of any
 * route's data layer, as the other builders in this folder are.
 */
function priceIndex(strikes: number[], price: number): number {
  if (strikes.length === 0) return 0;
  if (price <= strikes[0]!) return 0;
  const last = strikes.length - 1;
  if (price >= strikes[last]!) return last;
  for (let i = 0; i < last; i++) {
    const a = strikes[i]!;
    const b = strikes[i + 1]!;
    if (price >= a && price <= b) return i + (price - a) / (b - a);
  }
  return last;
}
