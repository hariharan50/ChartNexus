/**
 * Motion tokens for TypeScript — the same scale `app.css` declares as CSS
 * custom properties. Use these when motion has to be driven from script (the
 * Web Animations API, an ECharts `animationDuration`, a timeout that waits out
 * an exit) so the script and the stylesheet can never drift apart.
 *
 * Keep in step with the `--dur-*` / `--ease-*` block in `app/app.css`.
 */

export const duration = {
  /** Colour, fill, background-colour, border, focus ring. */
  xquick: 80,
  /** Opacity fades, icons, card hover, small transforms. */
  quick: 160,
  /** Dropdowns, popovers, menus, tooltips, overlay backdrops. */
  moderate: 280,
  /** Widths that grow — pair with `easing.decelerate`. */
  gentle: 360,
  /** Modals, drawers, side sheets. */
  slow: 480,
  /** Emphasis pulses only. */
  xslow: 640,
  /** Any exit: ~30% faster than the entrance it reverses. */
  exit: 200
} as const;

export const easing = {
  /** The default for almost everything. */
  standard: 'cubic-bezier(0.3, 0, 0.2, 1)',
  /** Things entering or expanding. */
  decelerate: 'cubic-bezier(0, 0, 0.2, 1)',
  /** Things leaving. */
  exit: 'ease-in'
} as const;

export type Duration = keyof typeof duration;
export type Easing = keyof typeof easing;

/** CSS references, for inline `style` props. */
export const cssVar = {
  duration: (d: Duration) => `var(--dur-${d})`,
  easing: (e: Easing) => `var(--ease-${e})`
} as const;

/**
 * Global utility classes defined in `app.css`. Apply one to an element that
 * mounts when its content is ready:
 *
 *   <div className={cx(s.panel, motionPresets.fadeIn)}>…</div>
 */
export const motionPresets = {
  /** 160ms opacity 0 → 1. Content arriving after a load. */
  fadeIn: 'cn-fade-in',
  /** 280ms translateY(4px) scale(0.98) → rest. Menus, popovers, listboxes. */
  dropIn: 'cn-drop-in',
  /** 280ms scale(0) → 1 with opacity. Toasts. */
  popIn: 'cn-pop-in',
  /** Soft 1.6s background pulse. Loading placeholders; see `<Skeleton>`. */
  skeleton: 'cn-skeleton'
} as const;

/** True when the user has asked the OS for less motion. SSR-safe. */
export function prefersReducedMotion(): boolean {
  return (
    typeof window !== 'undefined' &&
    typeof window.matchMedia === 'function' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches
  );
}
