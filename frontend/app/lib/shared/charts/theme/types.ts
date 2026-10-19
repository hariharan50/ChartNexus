/**
 * Every colour a chart is allowed to use.
 *
 * Charts must not name colours themselves — they ask for a role. The values are
 * resolved from the `--cn-*` design tokens at runtime, so all four themes work
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
  /**
   * Up and down — a price that rose, a sector advancing, a positive
   * contribution.
   *
   * Fixed to `--cn-bullish`/`--cn-bearish` and never affected by the Call /
   * Put Colour preference. A candle that closed lower is red in every
   * configuration of the app; a user who asks for red calls has not asked for
   * green down-candles, and giving them that is the one way this preference
   * can make a chart lie.
   */
  up: string;
  down: string;
  /**
   * The two sides of an option ladder.
   *
   * Reads `--cn-call-series`/`--cn-put-series`, which Settings › Global ›
   * Call / Put Colour swaps. Use these *only* where the colour encodes CE
   * versus PE — a call OI bar, a put IV line, a premium-decay leg. For
   * anything that encodes direction use `up`/`down` above, which is what
   * these two roles used to be before the preference existed.
   */
  call: string;
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
  /**
   * The eight categorical series slots, for charts that encode *identity*
   * rather than direction — currently the Index Weightage donut.
   *
   * Always assigned in order, never cycled: a ninth category folds into
   * "Other". The order is what makes the palette colour-vision-safe for the
   * pairs a chart puts next to each other, and it was validated against every
   * theme's own surface — see the note beside the tokens in `app.css`.
   *
   * Eight named roles rather than an array because the theme is a flat record
   * of token lookups; `seriesPalette()` in this folder hands them back as the
   * ordered list a chart actually wants.
   */
  series1: string;
  series2: string;
  series3: string;
  series4: string;
  series5: string;
  series6: string;
  series7: string;
  series8: string;
}
