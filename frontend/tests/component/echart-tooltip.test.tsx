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
  it('paints the option untouched while tooltips are on', () => {
    render(<EChart option={OPTION} resetKey="lot" />);

    expect(last().option).toBe(OPTION);
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
