import { useSyncExternalStore } from 'react';
import { readChartTheme, sameTheme, SERVER_CHART_THEME } from './tokens';
import type { ChartTheme } from './types';

/**
 * The chart colour palette for the theme currently on `<html>`.
 *
 * A CSS custom property changing is invisible to JavaScript — nothing fires, and
 * a canvas has already been painted with the old colours. The theme store writes
 * `data-theme` (and preferences write `data-callput`), so a MutationObserver on
 * those attributes is the signal.
 *
 * One observer and one cached snapshot are shared by every chart on the page.
 */

let snapshot: ChartTheme = SERVER_CHART_THEME;
let initialised = false;
const listeners = new Set<() => void>();

function recompute(): void {
  const next = readChartTheme();
  // A new object reference on every read would make useSyncExternalStore
  // consider the store changed forever and loop.
  if (sameTheme(next, snapshot)) return;
  snapshot = next;
  for (const listener of listeners) listener();
}

let observer: MutationObserver | undefined;

function subscribe(listener: () => void): () => void {
  if (!initialised) {
    snapshot = readChartTheme();
    initialised = true;
  }

  listeners.add(listener);

  observer ??= new MutationObserver(recompute);
  observer.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ['data-theme', 'data-callput']
  });

  return () => {
    listeners.delete(listener);
    if (listeners.size === 0) {
      observer?.disconnect();
      observer = undefined;
    }
  };
}

const getSnapshot = (): ChartTheme => {
  if (!initialised) {
    snapshot = readChartTheme();
    initialised = true;
  }
  return snapshot;
};

const getServerSnapshot = (): ChartTheme => SERVER_CHART_THEME;

export function useChartTheme(): ChartTheme {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}
