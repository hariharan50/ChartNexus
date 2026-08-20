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
  maxPainLabelBg: '--mc-brand-deep'
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
  maxPainLabelBg: 'rgb(140, 50, 18)'
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
