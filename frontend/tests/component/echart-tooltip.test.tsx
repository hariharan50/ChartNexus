import { render } from '@testing-library/react';
import { act } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { EChartsCoreOption } from '../../app/lib/shared/charts/echarts-modules';
import { usePreferencesStore } from '../../app/lib/shared/ui/preferences-store';

/**
 * Settings › Global › Show chart tooltip, at the one place it is applied.
 *
 * `EChart` is the app's only ECharts mount point, so these two assertions are
 * what make the preference global: every chart's option passes through here.
 */

interface Painted {
  option: EChartsCoreOption;
  resetKey?: string | undefined;
}

const painted: Painted[] = [];

vi.mock('../../app/lib/shared/charts/use-echart', () => ({
  useEChart: (args: Painted) => {
    painted.push({ option: args.option, resetKey: args.resetKey });
    return { current: undefined };
  }
}));

const { default: EChart } = await import('../../app/lib/shared/charts/EChart');

const OPTION = { tooltip: { trigger: 'axis' }, series: [] } as EChartsCoreOption;
const last = () => painted[painted.length - 1]!;
const tooltipOf = (p: Painted) => (p.option as { tooltip: Record<string, unknown> }).tooltip;

beforeEach(() => {
  painted.length = 0;
  usePreferencesStore.setState({ showChartTooltip: true });
});

describe('EChart and the tooltip preference', () => {
  it('leaves the tooltip and the reset key alone while tooltips are on', () => {
    render(<EChart option={OPTION} resetKey="lot" />);

    // The tooltip itself passes through by identity — this transform is the
    // only thing that may touch it, and with the preference on it does not.
    //
    // The *option* is no longer identical, because `withMotionDefaults` adds
    // the house animation duration on this same seam. That is deliberate: the
    // charts animate inside a canvas no stylesheet reaches, so the default had
    // to be applied somewhere, and this is the one place every chart passes
    // through. What still has to hold is the reset key, which is what decides
    // whether a chart repaints by merge or by rebuild.
    expect(tooltipOf(last())).toBe(OPTION.tooltip);
    expect(last().resetKey).toBe('lot');
  });

  it('suppresses the tooltip for every chart when the preference is off', () => {
    usePreferencesStore.setState({ showChartTooltip: false });

    render(<EChart option={OPTION} />);

    expect(tooltipOf(last()).showContent).toBe(false);
    expect(tooltipOf(last()).trigger).toBe('axis');
  });

  it('rebuilds rather than merges when the preference changes', () => {
    // `setOption` merges, and a merge can set `showContent: false` but cannot
    // clear it — so a chart that was mounted while tooltips were off would
    // stay silent forever. A different reset key routes it through
    // `chart.clear()` instead. This is the whole reason the key is derived.
    render(<EChart option={OPTION} resetKey="lot" />);
    const before = last().resetKey;

    act(() => usePreferencesStore.setState({ showChartTooltip: false }));
    const off = last().resetKey;

    act(() => usePreferencesStore.setState({ showChartTooltip: true }));

    expect(off).not.toBe(before);
    expect(last().resetKey).toBe(before);
  });
});
