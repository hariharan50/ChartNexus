import type { EChartsCoreOption } from '../echarts-modules';
import { withAlpha } from '../theme/tokens';
import type { ChartTheme } from '../theme/types';

/**
 * The Open Interest bar chart, as data.
 *
 * Pure on purpose: no React, no DOM, no ECharts instance. Everything the chart
 * shows is a function of these inputs, so its behaviour — which series exist in
 * each mode, where the spot and max-pain markers land, how an OI decrease is
 * drawn — is unit-testable without rendering anything.
 */

/** A per-strike bar row. Structurally the `OiBar` from the Open Interest page. */
export interface OiChartBar {
  strike: number;
  callNow: number;
  putNow: number;
  callOpen: number;
  putOpen: number;
  callChg: number;
  putChg: number;
  atm: boolean;
}

export type OiChartMode = 'change_total' | 'change' | 'total';

export interface OpenInterestInput {
  bars: OiChartBar[];
  mode: OiChartMode;
  spot: number;
  maxPain: number;
  /** Call-side colour. Owned by the Open Interest tool, not the global theme. */
  callColor: string;
  putColor: string;
  showTooltip: boolean;
  /** Formats an OI magnitude for the axis and the tooltip. */
  formatOi: (value: number) => string;
  /** Same, but always signed. */
  formatSigned: (value: number) => string;
  /** Column headings inside the tooltip, e.g. "9:15 am" and "10:46 am". */
  openLabel: string;
  nowLabel: string;
}

/**
 * Fractional category index for a price, so a spot line can land between two
 * strike columns rather than snapping onto one.
 */
export function priceIndex(strikes: number[], price: number): number {
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

/**
 * A per-bar style for a "change" magnitude: hatched fill on an increase,
 * hollow on a decrease. The shape carries the sign, so the direction survives
 * for anyone who cannot separate the two hues.
 *
 * Every number here is chosen to stay legible at small bar widths, which is
 * where the previous styling fell apart:
 *
 * - **Opaque fill, stripes cut in the surface colour.** A translucent fill with
 *   translucent stripes over it put two low-contrast layers on top of each
 *   other; the hatch read as a wash rather than as stripes. Solid bar, holes
 *   punched through to the panel behind it, is the highest contrast available
 *   and it is what every charting package that gets this right does.
 * - **5px stripes, not 1px.** A one-pixel mark is the most fragile thing you can
 *   put on a chart: it is the first casualty of any scaling, and at a 24px bar
 *   width the eye reads a 1px/6px hatch as a flat tint anyway.
 * - **1px borders, not 1.5px.** A 1.5px stroke cannot align to a pixel boundary
 *   at any common display scaling, so it is always drawn as a soft two-pixel
 *   smear. 1px lands cleanly.
 * - **A solid border on the hollow bar, not a dashed one.** Hollow-versus-filled
 *   already carries the sign without relying on colour; the dashes added nothing
 *   to that and cost the outline its definition.
 */
function changeStyle(value: number, color: string, theme: ChartTheme) {
  if (value >= 0) {
    return {
      color,
      borderColor: color,
      borderWidth: 1,
      decal: {
        symbol: 'rect',
        color: theme.surface,
        dashArrayX: [5, 6],
        dashArrayY: [6, 0],
        rotation: -Math.PI / 4
      }
    };
  }
  return {
    color: 'transparent',
    borderColor: color,
    borderWidth: 1
  };
}

function overlays(input: OpenInterestInput, theme: ChartTheme) {
  const { bars, spot, maxPain } = input;
  const strikes = bars.map((b) => b.strike);
  const atmIdx = bars.findIndex((b) => b.atm);
  const mpIdx = bars.findIndex((b) => b.strike === maxPain);

  const markArea =
    atmIdx >= 0
      ? {
          silent: true,
          itemStyle: { color: withAlpha(theme.atmBand, 0.12) },
          data: [[{ xAxis: atmIdx - 0.5 }, { xAxis: atmIdx + 0.5 }]]
        }
      : undefined;

  const lines: Record<string, unknown>[] = [];
  if (Number.isFinite(spot) && spot > 0) {
    lines.push({
      xAxis: priceIndex(strikes, spot),
      lineStyle: { color: theme.marker, type: 'dashed', width: 1.5 },
      label: {
        show: true,
        position: 'start',
        formatter: `Spot: ${Math.round(spot)}`,
        color: theme.spotLabelText,
        backgroundColor: theme.spotLabelBg,
        padding: [3, 6],
        borderRadius: 4,
        fontSize: 11
      }
    });
  }
  if (mpIdx >= 0) {
    lines.push({
      xAxis: mpIdx,
      lineStyle: { color: theme.marker, type: 'dashed', width: 1.5 },
      label: {
        show: true,
        position: 'end',
        formatter: `Max Pain: ${maxPain}`,
        color: theme.onMarker,
        backgroundColor: theme.maxPainLabelBg,
        padding: [3, 6],
        borderRadius: 4,
        fontSize: 11
      }
    });
  }

  return { markArea, markLine: { silent: true, symbol: 'none', data: lines } };
}

function seriesFor(input: OpenInterestInput, theme: ChartTheme) {
  const { bars, mode, callColor, putColor } = input;
  const { markArea, markLine } = overlays(input, theme);
  const base = { type: 'bar' as const, barMaxWidth: 24, barGap: '18%', barCategoryGap: '34%' };

  if (mode === 'total') {
    return [
      {
        ...base,
        name: 'Call',
        stack: 'call',
        itemStyle: { color: callColor, borderRadius: [4, 4, 0, 0] },
        data: bars.map((b) => b.callNow),
        markArea,
        markLine
      },
      {
        ...base,
        name: 'Put',
        stack: 'put',
        itemStyle: { color: putColor, borderRadius: [4, 4, 0, 0] },
        data: bars.map((b) => b.putNow)
      }
    ];
  }

  if (mode === 'change') {
    return [
      {
        ...base,
        name: 'Call',
        stack: 'call',
        data: bars.map((b) => ({
          value: Math.abs(b.callChg),
          itemStyle: changeStyle(b.callChg, callColor, theme)
        })),
        markArea,
        markLine
      },
      {
        ...base,
        name: 'Put',
        stack: 'put',
        data: bars.map((b) => ({
          value: Math.abs(b.putChg),
          itemStyle: changeStyle(b.putChg, putColor, theme)
        }))
      }
    ];
  }

  // change_total: solid base = min(open, now), change segment styled on top.
  return [
    {
      ...base,
      name: 'Call',
      stack: 'call',
      itemStyle: { color: callColor },
      data: bars.map((b) => Math.min(b.callOpen, b.callNow)),
      markArea,
      markLine
    },
    {
      ...base,
      name: 'CallChg',
      stack: 'call',
      // Square, unlike the solid `total` bars: a 3px radius bent a 1px outline
      // around an arc at the top of every hollow bar, which read as a blurred
      // capsule rather than a bar. It also has to sit flush on the solid base
      // segment beneath it.
      data: bars.map((b) => ({
        value: Math.abs(b.callChg),
        itemStyle: changeStyle(b.callChg, callColor, theme)
      }))
    },
    {
      ...base,
      name: 'Put',
      stack: 'put',
      itemStyle: { color: putColor },
      data: bars.map((b) => Math.min(b.putOpen, b.putNow))
    },
    {
      ...base,
      name: 'PutChg',
      stack: 'put',
      data: bars.map((b) => ({
        value: Math.abs(b.putChg),
        itemStyle: changeStyle(b.putChg, putColor, theme)
      }))
    }
  ];
}

export function tooltipHtml(input: OpenInterestInput, index: number): string {
  const { bars, callColor, putColor, formatOi, formatSigned, openLabel, nowLabel } = input;
  const b = bars[index];
  if (!b) return '';

  const line = (label: string, chg: number, pct: number) =>
    `<div style="color:${chg >= 0 ? callColor : putColor}">${label}: ${formatSigned(chg)} (${pct >= 0 ? '+' : ''}${pct.toFixed(1)}%)</div>`;

  const callPct = b.callOpen ? (b.callChg / b.callOpen) * 100 : 0;
  const putPct = b.putOpen ? (b.putChg / b.putOpen) * 100 : 0;

  return `
      <div style="font-weight:700;margin-bottom:4px">${b.strike}${b.atm ? ' · ATM' : ''}</div>
      <div style="color:${callColor};font-weight:600">Call</div>
      <div>OI @ ${openLabel}: ${formatOi(b.callOpen)}</div>
      ${line('OI Chg', b.callChg, callPct)}
      <div>OI @ ${nowLabel}: ${formatOi(b.callNow)}</div>
      <div style="color:${putColor};font-weight:600;margin-top:4px">Put</div>
      <div>OI @ ${openLabel}: ${formatOi(b.putOpen)}</div>
      ${line('OI Chg', b.putChg, putPct)}
      <div>OI @ ${nowLabel}: ${formatOi(b.putNow)}</div>`;
}

export function buildOpenInterestOption(
  input: OpenInterestInput,
  theme: ChartTheme
): EChartsCoreOption {
  const { bars, showTooltip, formatOi } = input;
  const atmStrike = bars.find((b) => b.atm)?.strike;

  return {
    backgroundColor: 'transparent',
    grid: { left: 8, right: 24, top: 28, bottom: 8, containLabel: true },
    tooltip: showTooltip
      ? {
          trigger: 'axis',
          axisPointer: { type: 'shadow' },
          // The chart sits in an `overflow-x: auto` wrapper so wide ladders can
          // scroll, and that wrapper clips its own descendants — which cut the
          // tooltip off mid-number ("OI @ 9:1…"). Rendering it on the body puts
          // it outside that clipping context entirely.
          appendTo: 'body',
          backgroundColor: theme.tooltipBg,
          borderColor: theme.grid,
          textStyle: { color: theme.tooltipText, fontSize: 12 },
          formatter: (params: unknown) => {
            const arr = params as Array<{ dataIndex: number }>;
            return arr.length ? tooltipHtml(input, arr[0]!.dataIndex) : '';
          }
        }
      : { show: false },
    xAxis: {
      type: 'category',
      data: bars.map((b) => String(b.strike)),
      axisLine: { lineStyle: { color: theme.grid } },
      axisTick: { show: false },
      axisLabel: {
        interval: 0,
        color: theme.axis,
        fontSize: 11,
        formatter: (val: string) => (Number(val) === atmStrike ? `{atm|${val}}` : val),
        rich: { atm: { color: theme.marker, fontWeight: 'bold' } }
      }
    },
    yAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: theme.grid } },
      axisLabel: {
        color: theme.axis,
        fontSize: 11,
        formatter: (v: number) => formatOi(v)
      }
    },
    series: seriesFor(input, theme)
  };
}
