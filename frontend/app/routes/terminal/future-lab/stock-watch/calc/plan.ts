/**
 * Trade planning and scenario analysis for a long option.
 *
 * **Long options only, and the validator enforces it.** A stop above entry or
 * a target below it is not an exotic configuration this calculator declines to
 * model — on a long call or put it is arithmetic that would produce a negative
 * risk and a reward-to-risk ratio with the wrong sign. It is rejected with a
 * reason rather than computed.
 *
 * **The lot size is never assumed.** It comes from the instrument catalog,
 * which loads the exchange symbol master. Indian F&O lot sizes differ per
 * underlying and are revised by circular; a hard-coded 50 or 75 would size
 * every stock trade wrong and would do it silently.
 *
 * **Costs are configured, not guessed.** Brokerage, STT, exchange charges,
 * stamp duty and GST vary by broker and by plan. This module takes rates and
 * applies them; it does not ship a default fee schedule claiming to be anyone's
 * actual charges.
 *
 * Nothing here is a quote. Scenario premiums come from Black-Scholes on a
 * volatility *you* supply, and the stop-loss figure is the price you intend,
 * not the price you will get — a gap through it fills where the market is, and
 * the planner says so rather than implying the loss is capped.
 */

import {
  type OptionType,
  breakeven,
  greeks,
  price,
  volFromPercent,
  yearsFromDays
} from './black-scholes';

export interface CostRates {
  /** Flat brokerage per executed order, in rupees. Two orders per round trip. */
  brokeragePerOrder: number;
  /** Securities transaction tax, percent of the *sell* premium turnover. */
  sttPercentOnSell: number;
  /** Exchange transaction charges, percent of premium turnover both ways. */
  exchangePercent: number;
  /** SEBI turnover fee, percent of premium turnover both ways. */
  sebiPercent: number;
  /** Stamp duty, percent of the *buy* premium turnover. */
  stampPercentOnBuy: number;
  /** GST, percent applied to brokerage plus exchange and SEBI charges. */
  gstPercent: number;
  /** Expected slippage per unit, in rupees, applied on entry and on exit. */
  slippagePerUnit: number;
}

/**
 * All zero.
 *
 * Deliberately not a plausible-looking Indian retail schedule. A number the
 * user did not enter, rendered as "estimated charges", is a number they will
 * plan around — and every broker's is different. The panel prompts for them
 * and shows costs as excluded until they are supplied.
 */
export const NO_COSTS: CostRates = {
  brokeragePerOrder: 0,
  sttPercentOnSell: 0,
  exchangePercent: 0,
  sebiPercent: 0,
  stampPercentOnBuy: 0,
  gstPercent: 0,
  slippagePerUnit: 0
};

export interface PlanInput {
  type: OptionType;
  strike: number;
  expiry: string;
  /** From the instrument catalog. Never defaulted. */
  lotSize: number;
  lots: number;
  entryPremium: number;
  stopPremium: number;
  targetPremium: number;
  /** Trading capital the risk budget is a percentage of. */
  capital: number;
  /** Percent of capital risked on this trade. */
  riskPercent: number;
  /** Rupee cap on losses for the day; the plan reports what is left. */
  maxDailyLoss?: number | undefined;
  /** Rupees already lost today, so the remaining budget is real. */
  lossSoFarToday?: number | undefined;
  costs?: CostRates | undefined;
}

export interface PlanIssue {
  field: keyof PlanInput | 'general';
  message: string;
  severity: 'error' | 'warning';
}

export interface TradePlan {
  valid: boolean;
  issues: PlanIssue[];
  /** Rupees at risk per unit of the contract. */
  riskPerUnit: number;
  riskPerLot: number;
  /** Risk on the planned number of lots, before costs. */
  plannedRisk: number;
  rewardPerUnit: number;
  rewardPerLot: number;
  plannedReward: number;
  /** Reward ÷ risk, before costs. `undefined` when risk is zero. */
  rewardToRisk?: number | undefined;
  /** Capital × riskPercent — what the plan is allowed to lose. */
  riskBudget: number;
  /** Lots the budget actually permits. Zero means the stop is too wide. */
  maxLots: number;
  /** Premium outlay for the planned lots. */
  premiumOutlay: number;
  /** Round-trip charges on the planned position, at the configured rates. */
  estimatedCosts: number;
  /** Net result at target and at stop, after costs and slippage. */
  netAtTarget: number;
  netAtStop: number;
  /** Underlying level where a long position breaks even at expiry, pre-cost. */
  breakevenLevel: number;
  /** Remaining daily loss budget after this trade's planned loss. */
  remainingDailyRisk?: number | undefined;
  /** True when no cost rates were supplied, so costs are excluded, not zero. */
  costsExcluded: boolean;
}

function costOf(rates: CostRates, buyTurnover: number, sellTurnover: number, orders = 2): number {
  const turnover = buyTurnover + sellTurnover;
  const brokerage = rates.brokeragePerOrder * orders;
  const exchange = (turnover * rates.exchangePercent) / 100;
  const sebi = (turnover * rates.sebiPercent) / 100;
  const stt = (sellTurnover * rates.sttPercentOnSell) / 100;
  const stamp = (buyTurnover * rates.stampPercentOnBuy) / 100;
  const gst = ((brokerage + exchange + sebi) * rates.gstPercent) / 100;
  return brokerage + exchange + sebi + stt + stamp + gst;
}

/** Whether any rate is non-zero — i.e. the user actually configured charges. */
export function costsConfigured(rates: CostRates): boolean {
  return Object.values(rates).some((rate) => rate > 0);
}

export function validate(input: PlanInput): PlanIssue[] {
  const issues: PlanIssue[] = [];
  const bad = (field: PlanIssue['field'], message: string) =>
    issues.push({ field, message, severity: 'error' });

  if (!(input.lotSize > 0)) {
    bad('lotSize', 'No lot size for this contract — the catalog has not supplied one.');
  }
  if (!Number.isInteger(input.lots) || input.lots < 1) {
    bad('lots', 'Lots must be a whole number, at least 1.');
  }
  if (!(input.entryPremium > 0)) bad('entryPremium', 'Entry premium must be above zero.');
  if (!(input.stopPremium >= 0)) bad('stopPremium', 'Stop premium cannot be negative.');
  if (!(input.targetPremium > 0)) bad('targetPremium', 'Target premium must be above zero.');

  // The long-option constraint. Stated as what it is rather than silently
  // producing a negative risk and an R:R with an inverted sign.
  if (input.entryPremium > 0 && input.stopPremium >= input.entryPremium) {
    bad(
      'stopPremium',
      'On a long option the stop must be below entry — above it, the "stop" is a profit.'
    );
  }
  if (input.entryPremium > 0 && input.targetPremium <= input.entryPremium) {
    bad(
      'targetPremium',
      'On a long option the target must be above entry — below it, the "target" is a loss.'
    );
  }
  if (!(input.capital > 0)) bad('capital', 'Capital must be above zero to size a position.');
  if (!(input.riskPercent > 0) || input.riskPercent > 100) {
    bad('riskPercent', 'Risk per trade must be between 0 and 100 percent.');
  }
  if (input.riskPercent > 5) {
    issues.push({
      field: 'riskPercent',
      message: `${input.riskPercent}% of capital on one option trade is a large single bet.`,
      severity: 'warning'
    });
  }
  return issues;
}

export function plan(input: PlanInput): TradePlan {
  const costs = input.costs ?? NO_COSTS;
  const costsExcluded = !costsConfigured(costs);
  const issues = validate(input);
  const valid = !issues.some((issue) => issue.severity === 'error');

  const riskPerUnit = Math.max(0, input.entryPremium - input.stopPremium);
  const rewardPerUnit = Math.max(0, input.targetPremium - input.entryPremium);
  const lotSize = Math.max(0, input.lotSize);
  const lots = Math.max(0, Math.floor(input.lots));

  const riskPerLot = riskPerUnit * lotSize;
  const rewardPerLot = rewardPerUnit * lotSize;
  const plannedRisk = riskPerLot * lots;
  const plannedReward = rewardPerLot * lots;
  const riskBudget = (input.capital * input.riskPercent) / 100;
  const maxLots = riskPerLot > 0 ? Math.floor(riskBudget / riskPerLot) : 0;

  const units = lotSize * lots;
  const premiumOutlay = input.entryPremium * units;

  // Slippage is applied twice — a worse fill in and a worse fill out — because
  // that is what it costs. Counting it once flatters every plan.
  const slip = costs.slippagePerUnit * units * 2;
  const sellAtTarget = input.targetPremium * units;
  const sellAtStop = input.stopPremium * units;
  const costAtTarget = costOf(costs, premiumOutlay, sellAtTarget) + slip;
  const costAtStop = costOf(costs, premiumOutlay, sellAtStop) + slip;

  const plannedLoss = plannedRisk + costAtStop;
  const remaining =
    input.maxDailyLoss != null
      ? input.maxDailyLoss - (input.lossSoFarToday ?? 0) - plannedLoss
      : undefined;

  const result: TradePlan = {
    valid,
    issues,
    riskPerUnit,
    riskPerLot,
    plannedRisk,
    rewardPerUnit,
    rewardPerLot,
    plannedReward,
    riskBudget,
    maxLots,
    premiumOutlay,
    estimatedCosts: costAtTarget,
    netAtTarget: plannedReward - costAtTarget,
    netAtStop: -(plannedRisk + costAtStop),
    breakevenLevel: breakeven(input.type, input.strike, input.entryPremium),
    costsExcluded
  };
  if (remaining != null) result.remainingDailyRisk = remaining;
  return result;
}

// -- scenarios ----------------------------------------------------------------

export interface ScenarioInput {
  type: OptionType;
  strike: number;
  /** Underlying now. */
  spot: number;
  /** Implied volatility now, in percent as the chain quotes it. */
  iv: number;
  /** Calendar days to expiry now. */
  days: number;
  entryPremium: number;
  lotSize: number;
  lots: number;
}

export interface ScenarioCell {
  /** Underlying move applied, in percent. */
  spotMovePercent: number;
  spot: number;
  /** IV change applied, in volatility points. */
  ivChange: number;
  iv: number;
  /** Calendar days elapsed from now. */
  daysElapsed: number;
  daysLeft: number;
  /** Theoretical premium under this scenario. Not a quote. */
  premium: number;
  pnlPerUnit: number;
  pnlPerLot: number;
  pnlPosition: number;
  delta: number;
  gamma: number;
  theta: number;
  vega: number;
  /** True when `daysLeft` is zero — the payoff, not a model price. */
  atExpiry: boolean;
}

/**
 * Reprice a contract under a change in underlying, volatility and time.
 *
 * At expiry the premium is the payoff — `max(0, S−K)` or `max(0, K−S)` — not a
 * Black-Scholes value with a tiny time stub, which would return a few paise of
 * optimism on a contract that is worthless.
 */
export function scenario(
  input: ScenarioInput,
  move: { spotMovePercent: number; ivChange: number; daysElapsed: number }
): ScenarioCell {
  const spot = input.spot * (1 + move.spotMovePercent / 100);
  const iv = Math.max(0, input.iv + move.ivChange);
  const daysLeft = Math.max(0, input.days - move.daysElapsed);
  const years = yearsFromDays(daysLeft);
  const vol = volFromPercent(iv);

  const leg = { type: input.type, spot, strike: input.strike, years, vol };
  const premium = price(leg);
  const sensitivities = daysLeft > 0 ? greeks(leg) : { delta: 0, gamma: 0, theta: 0, vega: 0 };

  const pnlPerUnit = premium - input.entryPremium;
  const pnlPerLot = pnlPerUnit * input.lotSize;

  return {
    spotMovePercent: move.spotMovePercent,
    spot,
    ivChange: move.ivChange,
    iv,
    daysElapsed: move.daysElapsed,
    daysLeft,
    premium,
    pnlPerUnit,
    pnlPerLot,
    pnlPosition: pnlPerLot * input.lots,
    delta: sensitivities.delta,
    gamma: sensitivities.gamma,
    theta: sensitivities.theta,
    vega: sensitivities.vega,
    atExpiry: daysLeft === 0
  };
}

/** A grid of scenarios across underlying moves, at one IV and time shift. */
export function scenarioRow(
  input: ScenarioInput,
  moves: number[],
  shift: { ivChange: number; daysElapsed: number }
): ScenarioCell[] {
  return moves.map((spotMovePercent) =>
    scenario(input, { spotMovePercent, ivChange: shift.ivChange, daysElapsed: shift.daysElapsed })
  );
}

/** The default ladder of underlying moves the grid is drawn across. */
export const DEFAULT_MOVES = [-5, -3, -2, -1, 0, 1, 2, 3, 5];

// -- comparison ---------------------------------------------------------------

export interface ComparisonInput {
  strike: number;
  type: OptionType;
  expiry: string;
  ltp: number;
  bid?: number | undefined;
  ask?: number | undefined;
  volume: number;
  oi: number;
  iv?: number | undefined;
  lotSize: number;
  delta?: number | undefined;
  gamma?: number | undefined;
  theta?: number | undefined;
  vega?: number | undefined;
}

export interface ComparisonRow extends ComparisonInput {
  /** Premium for one lot — the cash actually required. */
  premiumPerLot: number;
  spread?: number | undefined;
  spreadPercent?: number | undefined;
  breakevenLevel: number;
  /** Theta as a share of the premium, per day. How fast the clock eats it. */
  thetaPercentPerDay?: number | undefined;
}

/**
 * Derive the comparable figures for a shortlist of contracts.
 *
 * No ranking and no "best" flag. The highest volume, the lowest premium and
 * the tightest spread are three different contracts most days, and which one
 * is right depends on the trade — which this module does not know.
 */
export function compare(contracts: ComparisonInput[]): ComparisonRow[] {
  return contracts.map((contract) => {
    const spread =
      contract.bid != null && contract.ask != null ? contract.ask - contract.bid : undefined;
    const mid =
      contract.bid != null && contract.ask != null ? (contract.ask + contract.bid) / 2 : undefined;

    const row: ComparisonRow = {
      ...contract,
      premiumPerLot: contract.ltp * contract.lotSize,
      breakevenLevel: breakeven(contract.type, contract.strike, contract.ltp)
    };
    if (spread != null) row.spread = spread;
    if (spread != null && mid != null && mid > 0) row.spreadPercent = (spread / mid) * 100;
    if (contract.theta != null && contract.ltp > 0) {
      row.thetaPercentPerDay = (Math.abs(contract.theta) / contract.ltp) * 100;
    }
    return row;
  });
}
