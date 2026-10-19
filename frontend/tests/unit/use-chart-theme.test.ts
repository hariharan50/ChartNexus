import { renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { SERVER_CHART_THEME } from '../../app/lib/shared/charts/theme/tokens';
import type * as Tokens from '../../app/lib/shared/charts/theme/tokens';
import type { ChartTheme } from '../../app/lib/shared/charts/theme/types';

/**
 * The bridge between a CSS custom property and a painted canvas.
 *
 * A token changing fires no event and repaints no canvas, so the hook caches
 * one snapshot behind a MutationObserver on `<html>`. The subtlety is that the
 * observer only exists while a chart is mounted — and the two places a user
 * changes these tokens, Settings › Appearance and Settings › Global, are pages
 * with no chart on them.
 */

const current = { value: SERVER_CHART_THEME };

vi.mock('../../app/lib/shared/charts/theme/tokens', async (importOriginal) => {
  const actual = await importOriginal<typeof Tokens>();
  return { ...actual, readChartTheme: () => current.value };
});

// Imported after the mock is registered, so the hook closes over the stub.
const { useChartTheme } = await import('../../app/lib/shared/charts/theme/use-chart-theme');

function paletteWhere(call: string): ChartTheme {
  return { ...SERVER_CHART_THEME, call };
}

beforeEach(() => {
  current.value = SERVER_CHART_THEME;
});

afterEach(() => {
  document.documentElement.removeAttribute('data-callput');
});

describe('useChartTheme', () => {
  it('reads the live palette on mount', () => {
    current.value = paletteWhere('rgb(1, 1, 1)');

    const { result } = renderHook(() => useChartTheme());

    expect(result.current.call).toBe('rgb(1, 1, 1)');
  });

  it('re-reads when a chart mounts after the document moved on', () => {
    // The Settings round trip: a chart was on screen, the user left for a page
    // with none (so the observer disconnected), flipped Call / Put Colour, and
    // came back. Without a re-read on the first new subscriber the chart
    // repaints from a snapshot taken before the preference changed.
    const first = renderHook(() => useChartTheme());
    expect(first.result.current.call).toBe(SERVER_CHART_THEME.call);
    first.unmount();

    current.value = paletteWhere('rgb(9, 9, 9)');
    document.documentElement.setAttribute('data-callput', 'inverted');

    const second = renderHook(() => useChartTheme());

    expect(second.result.current.call).toBe('rgb(9, 9, 9)');
  });

  it('hands every chart on a page the same object', () => {
    // One snapshot, shared — otherwise each chart would see a fresh object on
    // every render and `useMemo`s keyed on the theme would never hit.
    const a = renderHook(() => useChartTheme());
    const b = renderHook(() => useChartTheme());

    expect(a.result.current).toBe(b.result.current);
  });
});
