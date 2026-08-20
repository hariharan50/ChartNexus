/** The standard retracement ratios, in the order they're drawn top to bottom. */
export const FIB_LEVELS = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1] as const;

export interface FibLevel {
  level: (typeof FIB_LEVELS)[number];
  price: number;
}

/**
 * The price at each retracement level between two anchors.
 *
 * `to` is the more recent point (the second click) and sits at 0%; `from` is
 * the older point (the first click) and sits at 100% — the standard reading,
 * where the levels describe how far price has pulled back *from* the move
 * that just happened, not the move itself.
 */
export function fibLevelPrices(from: number, to: number): FibLevel[] {
  const span = to - from;
  return FIB_LEVELS.map((level) => ({ level, price: to - span * level }));
}
