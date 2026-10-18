/**
 * Black-Scholes, for the Stock Watch terminal's model-derived figures.
 *
 * **Why a second implementation exists.** The backend has one
 * (`options_analytics/domain/greeks_math.py`) and it stays the reference for
 * the chain-wide series the Options Lab draws. This one is here because the
 * scenario calculator reprices a contract on every keystroke — three sliders
 * against a grid of underlying moves — and a round trip per slider tick is not
 * a calculator, it is a form. The two agree on every convention below, and the
 * conventions are restated rather than linked so a change here is visibly a
 * change to a documented contract.
 *
 * **Conventions**, chosen to match a broker terminal, not a textbook:
 *
 * * `delta` — per unit of underlying; calls positive, puts negative, |δ| ≤ 1.
 * * `gamma` — delta change per one-rupee move. Same for calls and puts, and
 *   deliberately not rescaled: the raw figure is what every other screen in
 *   this app and in a terminal shows.
 * * `theta` — rupees per *calendar* day, negative for a long option. The
 *   annual BS theta over 365, which is the number quoted on a trading screen.
 * * `vega` — rupees per *one volatility point* (a 1% move in IV), i.e. raw BS
 *   vega × 0.01.
 *
 * **What this model is not.** European exercise, continuous hedging, constant
 * volatility, a flat 7% rate, no dividends. NSE stock options are
 * American-style, so a deep-ITM put in particular can trade above what this
 * returns. Values it produces are theoretical and are labelled as such
 * everywhere they are shown; they are not quotes and nothing can be filled at
 * them.
 */

/** Same rate the backend's IV solver and greeks assume. The two must not disagree. */
export const RISK_FREE_RATE = 0.07;

/** Brokers quote IV in percent (`13.2` meaning 13.2%). */
const IV_PERCENT = 100;

/** Below this a quote is noise rather than a volatility, and d1 explodes. */
const MIN_VOL = 1e-6;

const ONE_VOL_POINT = 0.01;
const DAYS_IN_YEAR = 365;

export type OptionType = 'CE' | 'PE';

export interface Greeks {
  delta: number;
  gamma: number;
  theta: number;
  vega: number;
}

export const ZERO_GREEKS: Greeks = { delta: 0, gamma: 0, theta: 0, vega: 0 };

export interface Leg {
  type: OptionType;
  /** Underlying price. */
  spot: number;
  strike: number;
  /** Year fraction to expiry. Zero means expiry day — see `intrinsicOf`. */
  years: number;
  /** Unit volatility: 0.14 is 14%. Use `volFromPercent` on a chain's IV. */
  vol: number;
  rate?: number | undefined;
}

/** A chain quotes IV as 13.2; the model wants 0.132. */
export function volFromPercent(iv: number | undefined | null): number {
  if (iv == null || !Number.isFinite(iv) || iv <= 0) return 0;
  return iv / IV_PERCENT;
}

/** Calendar days to a year fraction, floored at zero. */
export function yearsFromDays(days: number): number {
  return Math.max(0, days) / DAYS_IN_YEAR;
}

/**
 * Theoretical premium.
 *
 * Degenerate inputs — expiry day, no volatility, a non-positive price — return
 * the intrinsic value rather than NaN. Both are ordinary states of a live
 * chain (the whole board is degenerate at 15:29 on expiry day) and one bad leg
 * must not take out a grid.
 */
export function price(leg: Leg): number {
  const { type, spot, strike, years, vol } = leg;
  const rate = leg.rate ?? RISK_FREE_RATE;
  if (!(spot > 0) || !(strike > 0)) return 0;
  if (years <= 0 || vol < MIN_VOL) return intrinsicOf(type, spot, strike);

  const { d1, d2 } = ds(spot, strike, years, vol, rate);
  const discount = strike * Math.exp(-rate * years);
  return type === 'CE'
    ? spot * cdf(d1) - discount * cdf(d2)
    : discount * cdf(-d2) - spot * cdf(-d1);
}

/** The four sensitivities, in the units documented at the top of this file. */
export function greeks(leg: Leg): Greeks {
  const { type, spot, strike, years, vol } = leg;
  const rate = leg.rate ?? RISK_FREE_RATE;
  if (!(spot > 0) || !(strike > 0) || years <= 0 || vol < MIN_VOL) return ZERO_GREEKS;

  const { d1, d2 } = ds(spot, strike, years, vol, rate);
  const nd1 = pdf(d1);
  const discount = strike * Math.exp(-rate * years);
  const sqrtT = Math.sqrt(years);

  const delta = type === 'CE' ? cdf(d1) : cdf(d1) - 1;
  const gamma = nd1 / (spot * vol * sqrtT);
  const vega = spot * nd1 * sqrtT * ONE_VOL_POINT;

  const decay = -(spot * nd1 * vol) / (2 * sqrtT);
  const carry = rate * discount;
  const annualTheta = type === 'CE' ? decay - carry * cdf(d2) : decay + carry * cdf(-d2);

  return {
    delta: finite(delta),
    gamma: finite(gamma),
    theta: finite(annualTheta / DAYS_IN_YEAR),
    vega: finite(vega)
  };
}

/**
 * The volatility that reprices `premium` back to the market, or `undefined`.
 *
 * Bisection rather than Newton-Raphson: vega collapses toward zero on deep
 * wings and on expiry day, and a Newton step divided by it walks off to a
 * nonsense root or diverges outright. Bisection cannot, at the cost of a few
 * more iterations nobody can perceive.
 *
 * `undefined` rather than a number when the premium sits outside what the
 * model can produce at any volatility — below intrinsic, or above the
 * underlying. That is a quote problem, not a volatility, and returning the
 * bracket edge would publish 500% IV as if it meant something.
 */
export function impliedVol(
  leg: Omit<Leg, 'vol'>,
  premium: number,
  { tolerance = 1e-5, maxIterations = 80 } = {}
): number | undefined {
  if (!(premium > 0) || leg.years <= 0) return undefined;

  const intrinsic = intrinsicOf(leg.type, leg.spot, leg.strike);
  if (premium < intrinsic - tolerance) return undefined;

  let low = MIN_VOL;
  let high = 5; // 500% — past any volatility a listed contract trades at.
  if (price({ ...leg, vol: high }) < premium) return undefined;

  for (let i = 0; i < maxIterations; i += 1) {
    const mid = (low + high) / 2;
    const diff = price({ ...leg, vol: mid }) - premium;
    if (Math.abs(diff) < tolerance) return mid;
    if (diff > 0) high = mid;
    else low = mid;
  }
  return (low + high) / 2;
}

/** What the option is worth if expiry were now. Never negative. */
export function intrinsicOf(type: OptionType, spot: number, strike: number): number {
  return type === 'CE' ? Math.max(0, spot - strike) : Math.max(0, strike - spot);
}

/** Premium above intrinsic. Floored at zero: a leg trading below intrinsic is
    an arbitrage or a stale print, and a negative "time value" reads as neither. */
export function extrinsicOf(premium: number, intrinsic: number): number {
  return Math.max(0, premium - intrinsic);
}

/** Where the underlying has to be at expiry for a long option to break even. */
export function breakeven(type: OptionType, strike: number, premium: number): number {
  return type === 'CE' ? strike + premium : strike - premium;
}

function ds(spot: number, strike: number, years: number, vol: number, rate: number) {
  const sqrtT = Math.sqrt(years);
  const d1 = (Math.log(spot / strike) + (rate + (vol * vol) / 2) * years) / (vol * sqrtT);
  return { d1, d2: d1 - vol * sqrtT };
}

/** Standard normal PDF. */
function pdf(x: number): number {
  return Math.exp(-0.5 * x * x) / Math.sqrt(2 * Math.PI);
}

/**
 * Standard normal CDF, via Abramowitz & Stegun 7.1.26 on `erf`.
 *
 * Accurate to ~1.5e-7, which is four orders of magnitude finer than the paisa
 * these premiums are quoted in. `Math.erf` does not exist in JavaScript.
 */
function cdf(x: number): number {
  return 0.5 * (1 + erf(x / Math.SQRT2));
}

function erf(x: number): number {
  const sign = x < 0 ? -1 : 1;
  const z = Math.abs(x);
  const t = 1 / (1 + 0.3275911 * z);
  const poly =
    t *
    (0.254829592 + t * (-0.284496736 + t * (1.421413741 + t * (-1.453152027 + t * 1.061405429))));
  return sign * (1 - poly * Math.exp(-z * z));
}

function finite(value: number): number {
  return Number.isFinite(value) ? value : 0;
}
