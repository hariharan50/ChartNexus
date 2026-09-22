import type { ChartTheme } from './types';

/**
 * The `--mc-*` token behind each chart role.
 *
 * All of these already exist in app.css for every theme, so charts follow a
 * theme switch without any new tokens being defined.
 */
const CHART_TOKENS: Record<keyof ChartTheme, string> = {
  axis: '--mc-text-subtle',
  accent: '--mc-accent',
  grid: '--mc-border',
  surface: '--mc-surface',
  tooltipBg: '--mc-surface',
  tooltipText: '--mc-text',
  call: '--mc-bullish',
  put: '--mc-bearish',
  marker: '--mc-warning',
  atmBand: '--mc-warning',
  onMarker: '--mc-on-brand',
  spotLabelBg: '--mc-surface-raised',
  spotLabelText: '--mc-text',
  maxPainLabelBg: '--mc-brand-deep',
  series1: '--mc-series-1',
  series2: '--mc-series-2',
  series3: '--mc-series-3',
  series4: '--mc-series-4',
  series5: '--mc-series-5',
  series6: '--mc-series-6',
  series7: '--mc-series-7',
  series8: '--mc-series-8'
};

/**
 * What the server renders and the first client render must agree with.
 *
 * These are app.css's dark-theme values, copied literally. `getComputedStyle`
 * cannot run during SSR, and a chart is client-only anyway — this exists so
 * `useSyncExternalStore` has a stable server snapshot rather than throwing.
 */
export const SERVER_CHART_THEME: ChartTheme = Object.freeze({
  axis: 'rgb(125, 134, 156)',
  accent: 'rgb(76, 141, 255)',
  grid: 'rgb(38, 43, 58)',
  surface: 'rgb(19, 23, 34)',
  tooltipBg: 'rgb(19, 23, 34)',
  tooltipText: 'rgb(230, 233, 240)',
  call: 'rgb(23, 184, 119)',
  put: 'rgb(242, 73, 92)',
  marker: 'rgb(240, 173, 78)',
  atmBand: 'rgb(240, 173, 78)',
  onMarker: 'rgb(255, 255, 255)',
  spotLabelBg: 'rgb(26, 31, 46)',
  spotLabelText: 'rgb(230, 233, 240)',
  maxPainLabelBg: 'rgb(140, 50, 18)',
  series1: 'rgb(57, 135, 229)',
  series2: 'rgb(217, 89, 38)',
  series3: 'rgb(25, 158, 112)',
  series4: 'rgb(201, 133, 0)',
  series5: 'rgb(213, 81, 129)',
  series6: 'rgb(0, 131, 0)',
  series7: 'rgb(144, 133, 233)',
  series8: 'rgb(230, 103, 103)'
});

/**
 * Turns a declared token value into something a canvas can paint.
 *
 * `getPropertyValue('--x')` returns the *declared* text, which may be
 * `color-mix(...)`, `oklch(...)` or a bare hex. ECharts hands colours straight
 * to the canvas 2D context, which understands far less than CSS does. Bouncing
 * the value through a real element makes the browser resolve it to `rgb()`.
 */
function resolveColor(raw: string, probe: HTMLElement): string {
  probe.style.color = '';
  probe.style.color = raw.trim();
  const resolved = getComputedStyle(probe).color;
  return resolved || raw.trim();
}

/** Reads the live theme off the document. Client-only. */
export function readChartTheme(): ChartTheme {
  if (typeof document === 'undefined') return SERVER_CHART_THEME;

  const root = document.documentElement;
  const styles = getComputedStyle(root);

  const probe = document.createElement('span');
  probe.style.display = 'none';
  document.body.appendChild(probe);

  try {
    const entries = Object.entries(CHART_TOKENS) as Array<[keyof ChartTheme, string]>;
    const theme = {} as ChartTheme;
    for (const [role, token] of entries) {
      const raw = styles.getPropertyValue(token);
      theme[role] = raw ? resolveColor(raw, probe) : SERVER_CHART_THEME[role];
    }
    return theme;
  } finally {
    probe.remove();
  }
}

/** True when every role holds the same colour — used to avoid pointless repaints. */
export function sameTheme(a: ChartTheme, b: ChartTheme): boolean {
  return (Object.keys(CHART_TOKENS) as Array<keyof ChartTheme>).every(
    (role) => a[role] === b[role]
  );
}

/**
 * `rgba()` from either a resolved `rgb()`/`rgba()` string or a hex literal.
 *
 * Replaces the old `alpha(hex, a)` helper, which only understood `#rrggbb` and
 * would silently produce `rgba(NaN, …)` for a token that resolved to anything
 * else. Both forms are needed: theme roles arrive resolved to `rgb()`, while the
 * Open Interest tool's own Call/Put palette is still declared as hex.
 */
export function withAlpha(color: string, alpha: number): string {
  const trimmed = color.trim();

  const hex = /^#([\da-f]{3}|[\da-f]{6})$/i.exec(trimmed);
  if (hex) {
    const digits = hex[1]!;
    const full =
      digits.length === 3
        ? digits
            .split('')
            .map((c) => c + c)
            .join('')
        : digits;
    const n = Number.parseInt(full, 16);
    return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
  }

  const parts = trimmed.match(/-?[\d.]+/g);
  if (!parts || parts.length < 3) return trimmed;
  const [r, g, b] = parts;
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

/**
 * The categorical slots as the ordered list a chart consumes.
 *
 * Fixed order, and deliberately not a cycle: a chart with more categories than
 * slots must fold the tail into an "Other" bucket rather than reuse slot 1,
 * which would make two unrelated things the same colour on one plot.
 */
export function seriesPalette(theme: ChartTheme): readonly string[] {
  return [
    theme.series1,
    theme.series2,
    theme.series3,
    theme.series4,
    theme.series5,
    theme.series6,
    theme.series7,
    theme.series8
  ];
}
