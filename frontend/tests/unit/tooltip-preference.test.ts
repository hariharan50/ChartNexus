import { describe, expect, it } from 'vitest';
import { withoutTooltipContent } from '../../app/lib/shared/charts/tooltip-preference';
import type { EChartsCoreOption } from '../../app/lib/shared/charts/echarts-modules';

/**
 * Settings › Global › Show chart tooltip.
 *
 * One transform applied in `EChart`, so it reaches every chart in the app
 * without a flag threaded through twenty option builders.
 */

describe('withoutTooltipContent', () => {
  it('suppresses the floating box', () => {
    const out = withoutTooltipContent({ tooltip: { trigger: 'axis' } } as EChartsCoreOption);

    expect(out).toMatchObject({ tooltip: { showContent: false } });
  });

  it('keeps the axis pointer and the event behind it', () => {
    // `show: false` would drop the tooltip component outright, taking the
    // shadow band and `updateAxisPointer` with it — and Gamma Exposure drives
    // its side panel off that event. Turning off a tooltip must not turn off
    // a readout that was never a tooltip.
    const out = withoutTooltipContent({
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } }
    } as EChartsCoreOption) as { tooltip: Record<string, unknown> };

    expect(out.tooltip.show).toBeUndefined();
    expect(out.tooltip.axisPointer).toEqual({ type: 'shadow' });
  });

  it('leaves everything else on the option alone', () => {
    const option = {
      tooltip: { trigger: 'axis' },
      series: [{ type: 'bar' }],
      xAxis: { type: 'category' }
    } as EChartsCoreOption;

    const out = withoutTooltipContent(option) as Record<string, unknown>;

    expect(out.series).toBe((option as Record<string, unknown>).series);
    expect(out.xAxis).toBe((option as Record<string, unknown>).xAxis);
  });

  it('does not mutate the option it was given', () => {
    // The caller memoises the original; writing through it would leave the
    // chart unable to go back when the preference is switched on again.
    const option = { tooltip: { trigger: 'axis' } } as EChartsCoreOption;

    withoutTooltipContent(option);

    expect(option).toEqual({ tooltip: { trigger: 'axis' } });
  });

  it('handles a chart with no tooltip at all', () => {
    // The Max Pain gauge declares none.
    const option = { series: [] } as EChartsCoreOption;

    expect(withoutTooltipContent(option)).toBe(option);
  });

  it('handles a tooltip declared as an array', () => {
    const out = withoutTooltipContent({
      tooltip: [{ trigger: 'axis' }, { trigger: 'item' }]
    } as EChartsCoreOption) as { tooltip: Record<string, unknown>[] };

    expect(out.tooltip.map((one) => one.showContent)).toEqual([false, false]);
  });
});
