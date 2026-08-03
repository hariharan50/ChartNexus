/**
 * Number formatting for Indian markets.
 *
 * Open interest and cash flows are quoted in the Indian grouping system
 * (lakh/crore: 4,45,379 not 445,379), so we format with the `en-IN` locale
 * rather than the browser default.
 */

const inGrouping = new Intl.NumberFormat('en-IN');

/** Whole numbers with lakh/crore grouping — used for OI and volumes. */
export function formatInt(value: number): string {
  return inGrouping.format(Math.round(value));
}

/** A signed integer, e.g. OI change: `+16,642` / `−2,593`. */
export function formatSignedInt(value: number): string {
  const sign = value > 0 ? '+' : value < 0 ? '−' : '';
  return `${sign}${inGrouping.format(Math.abs(Math.round(value)))}`;
}

/** A price or index level to two decimals: `24,395.51`. */
export function formatPrice(value: number, fractionDigits = 2): string {
  return value.toLocaleString('en-IN', {
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits
  });
}

/** A signed percentage, already in percent units: `+0.82%` / `−0.54%`. */
export function formatSignedPercent(value: number, fractionDigits = 2): string {
  const sign = value > 0 ? '+' : value < 0 ? '−' : '';
  return `${sign}${Math.abs(value).toFixed(fractionDigits)}%`;
}

/** A plain percentage for IV-style columns: `17.0%`. */
export function formatPercent(value: number, fractionDigits = 1): string {
  return `${value.toFixed(fractionDigits)}%`;
}

/** Direction of a number, for colour + arrow decisions. */
export function direction(value: number): 'up' | 'down' | 'flat' {
  if (value > 0) return 'up';
  if (value < 0) return 'down';
  return 'flat';
}
