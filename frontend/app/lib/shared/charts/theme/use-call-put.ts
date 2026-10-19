import { useChartTheme } from './use-chart-theme';

/** The two option-side colours, as the user has chosen to read them. */
export interface CallPutColors {
  call: string;
  put: string;
}

/**
 * Call and Put, honouring Settings › Global › Call / Put Colour.
 *
 * The same two values `useChartTheme()` already carries as its `call`/`put`
 * roles — this exists for the many pages that want only the pair and would
 * otherwise pull the whole palette in just to name two colours. Both read the
 * same `--cn-call-series`/`--cn-put-series` tokens, so a page mixing the two
 * cannot end up with a chart and its legend disagreeing.
 *
 * Reactive: the preference writes `data-callput` on `<html>`, and the chart
 * theme's MutationObserver repaints on it. These were module constants
 * (`CALL_COLOR`/`PUT_COLOR` in the Open Interest page's data module) until the
 * preference existed, which is why so much of the app imported them; a
 * constant cannot change when the user flips the setting, so nothing should
 * reintroduce one.
 *
 * Derived values belong in a `useMemo` keyed on these — the object identity is
 * a new one on every render, so key on `call` and `put` rather than the object.
 */
export function useCallPutColors(): CallPutColors {
  const theme = useChartTheme();
  return { call: theme.call, put: theme.put };
}
