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
  /** Grid split lines and axis borders. */
  grid: string;
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
