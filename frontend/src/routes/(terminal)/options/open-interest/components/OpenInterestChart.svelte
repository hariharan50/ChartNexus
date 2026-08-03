<script lang="ts">
  import { onMount } from 'svelte';
  import * as echarts from 'echarts/core';
  import { BarChart } from 'echarts/charts';
  import {
    GridComponent,
    TooltipComponent,
    MarkLineComponent,
    MarkAreaComponent
  } from 'echarts/components';
  import { CanvasRenderer } from 'echarts/renderers';
  import {
    CALL_COLOR,
    PUT_COLOR,
    fmtOi,
    fmtSigned,
    priceIndex,
    type OiBar,
    type OiMode
  } from '../oi-data';

  echarts.use([
    BarChart,
    GridComponent,
    TooltipComponent,
    MarkLineComponent,
    MarkAreaComponent,
    CanvasRenderer
  ]);

  interface Props {
    bars: OiBar[];
    mode: OiMode;
    spot: number;
    maxPain: number;
    showLot: boolean;
    lotSize: number;
    isDark: boolean;
    showTooltip: boolean;
    openLabel: string;
    nowLabel: string;
  }

  let {
    bars,
    mode,
    spot,
    maxPain,
    showLot,
    lotSize,
    isDark,
    showTooltip,
    openLabel,
    nowLabel
  }: Props = $props();

  let el: HTMLDivElement;
  let chart: echarts.ECharts | undefined;
  // Tracks the unit the chart was last painted at; `undefined` until the first
  // effect run. A change forces a clear so the axis/label formatters repaint.
  let prevShowLot: boolean | undefined;

  const minWidth = $derived(Math.max(560, bars.length * 58));

  function alpha(hex: string, a: number): string {
    const n = parseInt(hex.slice(1), 16);
    return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${a})`;
  }

  // A per-bar style for a "change" magnitude: hatch decal on an increase,
  // dashed hollow border on a decrease.
  function changeStyle(value: number, color: string) {
    if (value >= 0) {
      return {
        color: alpha(color, 0.32),
        borderColor: color,
        borderWidth: 1.5,
        decal: {
          symbol: 'rect',
          color: alpha(color, 0.9),
          dashArrayX: [1, 6],
          dashArrayY: [4, 0],
          rotation: -Math.PI / 4
        }
      };
    }
    return {
      color: 'transparent',
      borderColor: color,
      borderWidth: 1.5,
      borderType: 'dashed' as const
    };
  }

  function overlays() {
    const strikes = bars.map((b) => b.strike);
    const atmIdx = bars.findIndex((b) => b.atm);
    const mpIdx = bars.findIndex((b) => b.strike === maxPain);

    const markArea =
      atmIdx >= 0
        ? {
            silent: true,
            itemStyle: { color: alpha('#f59e0b', 0.12) },
            data: [[{ xAxis: atmIdx - 0.5 }, { xAxis: atmIdx + 0.5 }]]
          }
        : undefined;

    const lines: Record<string, unknown>[] = [];
    if (Number.isFinite(spot) && spot > 0) {
      lines.push({
        xAxis: priceIndex(strikes, spot),
        lineStyle: { color: '#f59e0b', type: 'dashed', width: 1.5 },
        label: {
          show: true,
          position: 'start',
          formatter: `Spot: ${Math.round(spot)}`,
          color: '#fff',
          backgroundColor: '#1e293b',
          padding: [3, 6],
          borderRadius: 4,
          fontSize: 11
        }
      });
    }
    if (mpIdx >= 0) {
      lines.push({
        xAxis: mpIdx,
        lineStyle: { color: '#f59e0b', type: 'dashed', width: 1.5 },
        label: {
          show: true,
          position: 'end',
          formatter: `Max Pain: ${maxPain}`,
          color: '#fff',
          backgroundColor: '#b45309',
          padding: [3, 6],
          borderRadius: 4,
          fontSize: 11
        }
      });
    }

    return {
      markArea,
      markLine: {
        silent: true,
        symbol: 'none',
        data: lines
      }
    };
  }

  function seriesFor() {
    const call = bars.map((b) => b.callNow);
    const put = bars.map((b) => b.putNow);
    const { markArea, markLine } = overlays();
    const base = { type: 'bar' as const, barMaxWidth: 24, barGap: '18%', barCategoryGap: '34%' };

    if (mode === 'total') {
      return [
        {
          ...base,
          name: 'Call',
          stack: 'call',
          itemStyle: { color: CALL_COLOR, borderRadius: [4, 4, 0, 0] },
          data: call,
          markArea,
          markLine
        },
        {
          ...base,
          name: 'Put',
          stack: 'put',
          itemStyle: { color: PUT_COLOR, borderRadius: [4, 4, 0, 0] },
          data: put
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
            itemStyle: changeStyle(b.callChg, CALL_COLOR)
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
            itemStyle: changeStyle(b.putChg, PUT_COLOR)
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
        itemStyle: { color: CALL_COLOR },
        data: bars.map((b) => Math.min(b.callOpen, b.callNow)),
        markArea,
        markLine
      },
      {
        ...base,
        name: 'CallChg',
        stack: 'call',
        itemStyle: { borderRadius: [3, 3, 0, 0] },
        data: bars.map((b) => ({
          value: Math.abs(b.callChg),
          itemStyle: changeStyle(b.callChg, CALL_COLOR)
        }))
      },
      {
        ...base,
        name: 'Put',
        stack: 'put',
        itemStyle: { color: PUT_COLOR },
        data: bars.map((b) => Math.min(b.putOpen, b.putNow))
      },
      {
        ...base,
        name: 'PutChg',
        stack: 'put',
        itemStyle: { borderRadius: [3, 3, 0, 0] },
        data: bars.map((b) => ({
          value: Math.abs(b.putChg),
          itemStyle: changeStyle(b.putChg, PUT_COLOR)
        }))
      }
    ];
  }

  function tooltipHtml(index: number): string {
    const b = bars[index];
    if (!b) return '';
    const line = (label: string, chg: number, pct: number) =>
      `<div style="color:${chg >= 0 ? CALL_COLOR : PUT_COLOR}">${label}: ${fmtSigned(chg, showLot, lotSize)} (${pct >= 0 ? '+' : ''}${pct.toFixed(1)}%)</div>`;
    const callPct = b.callOpen ? (b.callChg / b.callOpen) * 100 : 0;
    const putPct = b.putOpen ? (b.putChg / b.putOpen) * 100 : 0;
    return `
      <div style="font-weight:700;margin-bottom:4px">${b.strike}${b.atm ? ' · ATM' : ''}</div>
      <div style="color:${CALL_COLOR};font-weight:600">Call</div>
      <div>OI @ ${openLabel}: ${fmtOi(b.callOpen, showLot, lotSize)}</div>
      ${line('OI Chg', b.callChg, callPct)}
      <div>OI @ ${nowLabel}: ${fmtOi(b.callNow, showLot, lotSize)}</div>
      <div style="color:${PUT_COLOR};font-weight:600;margin-top:4px">Put</div>
      <div>OI @ ${openLabel}: ${fmtOi(b.putOpen, showLot, lotSize)}</div>
      ${line('OI Chg', b.putChg, putPct)}
      <div>OI @ ${nowLabel}: ${fmtOi(b.putNow, showLot, lotSize)}</div>`;
  }

  function buildOption(): echarts.EChartsCoreOption {
    const axis = isDark ? '#64748b' : '#94a3b8';
    const grid = isDark ? '#1e293b' : '#e2e8f0';
    const atmStrike = bars.find((b) => b.atm)?.strike;

    return {
      backgroundColor: 'transparent',
      grid: { left: 8, right: 24, top: 28, bottom: 8, containLabel: true },
      tooltip: showTooltip
        ? {
            trigger: 'axis',
            axisPointer: { type: 'shadow' },
            backgroundColor: isDark ? '#0f172a' : '#ffffff',
            borderColor: grid,
            textStyle: { color: isDark ? '#e2e8f0' : '#0f172a', fontSize: 12 },
            formatter: (params: unknown) => {
              const arr = params as Array<{ dataIndex: number }>;
              return arr.length ? tooltipHtml(arr[0]!.dataIndex) : '';
            }
          }
        : { show: false },
      xAxis: {
        type: 'category',
        data: bars.map((b) => String(b.strike)),
        axisLine: { lineStyle: { color: grid } },
        axisTick: { show: false },
        axisLabel: {
          interval: 0,
          color: axis,
          fontSize: 11,
          formatter: (val: string) => (Number(val) === atmStrike ? `{atm|${val}}` : val),
          rich: { atm: { color: '#f59e0b', fontWeight: 'bold' } }
        }
      },
      yAxis: {
        type: 'value',
        splitLine: { lineStyle: { color: grid } },
        axisLabel: {
          color: axis,
          fontSize: 11,
          formatter: (v: number) => fmtOi(v, showLot, lotSize)
        }
      },
      series: seriesFor()
    };
  }

  onMount(() => {
    chart = echarts.init(el, undefined, { renderer: 'canvas' });
    chart.setOption(buildOption());
    const ro = new ResizeObserver(() => chart?.resize());
    ro.observe(el);
    return () => {
      ro.disconnect();
      chart?.dispose();
      chart = undefined;
    };
  });

  // Live updates keep the smooth replaceMerge path; a Show-Lot toggle must
  // clear first so the axis/label formatters repaint at the new unit.
  $effect(() => {
    if (!chart) return;
    const opt = buildOption();
    if (showLot !== prevShowLot) {
      chart.clear();
      chart.setOption(opt);
      prevShowLot = showLot;
    } else {
      chart.setOption(opt, { replaceMerge: ['series'] });
    }
  });
</script>

<div class="scroll">
  <div class="chart" bind:this={el} style="min-width: {minWidth}px"></div>
</div>

<style>
  .scroll {
    overflow-x: auto;
  }

  .chart {
    height: 424px;
  }
</style>
