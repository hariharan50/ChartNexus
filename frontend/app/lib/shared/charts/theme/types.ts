/**
 * Every colour a chart is allowed to use.
 *
 * Charts must not name colours themselves — they ask for a role. The values are
 * resolved from the `--mc-*` design tokens at runtime, so all four themes work
 * without a chart knowing any of them exist.
 */
export interface ChartTheme {
  /** Axis lines and tick labels. */
  axis: string;
  /**
   * The app's interactive blue, tuned per theme for contrast.
   *
   * For the one thing a chart is picking out — the active zone on the Max Pain
   * gauge. A literal blue would fail contrast on the light and warm themes,
   * which is exactly what a token exists to prevent.
   */
  accent: string;
  /** Grid split lines and axis borders. */
  grid: string;
  /**
   * The panel the chart is drawn on.
   *
   * For marks that have to read as *cut out of* a filled shape rather than
   * painted over it — the Open Interest hatch. Stripes in the surface colour on
   * an opaque bar give maximum stripe-to-fill contrast in every theme; stripes
   * in a translucent version of the bar's own colour give the least, which is
   * what made that hatch mush together.
   */
  surface: string;
  tooltipBg: string;
  tooltipText: string;
  /** Call-side series. */
  call: string;
  /** Put-side series. */
  put: string;
  /** Reference markers: spot, max pain. */
  marker: string;
  /** The ATM highlight band behind the bars. */
  atmBand: string;
  /** Text on a chip that is dark in every theme (`maxPainLabelBg`). */
  onMarker: string;
  /** Chip behind a spot marker's label — a raised app surface. */
  spotLabelBg: string;
  /**
   * Text on `spotLabelBg`.
   *
   * A separate role because `spotLabelBg` follows the theme's surface: it is
   * dark under `dark`/`terminal` and light under `light`/`warm`. Pairing it with
   * the always-white `onMarker` made the spot label vanish on the cream theme.
   */
  spotLabelText: string;
  /** Chip behind a max-pain marker's label — dark in every theme. */
  maxPainLabelBg: string;
}
