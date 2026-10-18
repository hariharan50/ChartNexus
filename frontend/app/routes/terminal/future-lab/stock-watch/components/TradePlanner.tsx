import { useMemo, useState } from 'react';
import { cx } from '$shared/ui/cx';
import type { OptionType } from '../calc/black-scholes';
import type { Leg } from '../calc/chain';
import { EMPTY, fmtDate, fmtPrice, fmtRupees, fmtRupeesPrecise } from '../calc/format';
import { type CostRates, type PlanInput, plan } from '../calc/plan';
import s from '../stock-watch.module.css';

export interface Selection {
  strike: number;
  type: OptionType;
  expiry: string;
  leg: Leg;
  lotSize?: number | undefined;
}

export interface PlannerInputs {
  lots: number;
  entry: number;
  stop: number;
  target: number;
  capital: number;
  riskPercent: number;
  maxDailyLoss: number;
  lossSoFarToday: number;
}

interface Props {
  selection?: Selection | undefined;
  inputs: PlannerInputs;
  onInputs: (next: PlannerInputs) => void;
  costs: CostRates;
  onCosts: (next: CostRates) => void;
  onJournal: () => void;
}

function NumberField({
  label,
  value,
  onChange,
  step = 0.05,
  min = 0,
  suffix,
  invalid
}: {
  label: string;
  value: number;
  onChange: (next: number) => void;
  step?: number | undefined;
  min?: number | undefined;
  suffix?: string | undefined;
  invalid?: boolean | undefined;
}) {
  return (
    <label className={cx(s.field, invalid && s.fieldError)}>
      <span className={s.fieldLabel}>
        {label}
        {suffix ? ` (${suffix})` : ''}
      </span>
      <input
        type="number"
        inputMode="decimal"
        step={step}
        min={min}
        value={Number.isFinite(value) ? value : ''}
        onChange={(event) => onChange(Number(event.target.value))}
      />
    </label>
  );
}

/**
 * Size a long call or put, and say what it costs if it is wrong.
 *
 * Recalculates on every keystroke because it runs entirely in the browser —
 * `calc/plan` is pure, so there is no round trip between typing a stop and
 * seeing the position it permits. That was the deciding argument against
 * putting this behind an endpoint.
 *
 * **The lot size is the contract's own**, read from the catalog. Indian F&O
 * lot sizes differ per underlying and move by circular; a planner that assumed
 * one would mis-size every trade on this page and would do it silently.
 */
export default function TradePlanner({
  selection,
  inputs,
  onInputs,
  costs,
  onCosts,
  onJournal
}: Props) {
  const [showCosts, setShowCosts] = useState(false);
  const lotSize = selection?.lotSize ?? 0;

  const result = useMemo(() => {
    if (!selection) return undefined;
    const input: PlanInput = {
      type: selection.type,
      strike: selection.strike,
      expiry: selection.expiry,
      lotSize,
      lots: inputs.lots,
      entryPremium: inputs.entry,
      stopPremium: inputs.stop,
      targetPremium: inputs.target,
      capital: inputs.capital,
      riskPercent: inputs.riskPercent,
      maxDailyLoss: inputs.maxDailyLoss || undefined,
      lossSoFarToday: inputs.lossSoFarToday,
      costs
    };
    return plan(input);
  }, [selection, lotSize, inputs, costs]);

  const set = (patch: Partial<PlannerInputs>) => onInputs({ ...inputs, ...patch });
  const errorsFor = (field: string) =>
    result?.issues.filter((issue) => issue.field === field && issue.severity === 'error') ?? [];

  return (
    <section className={s.panel}>
      <div className={s.panelHead}>
        <div>
          <h2 className={s.panelTitle}>Trade planner</h2>
          <p className={s.panelSub}>
            {selection
              ? `Long ${fmtPrice(selection.strike)} ${selection.type} · ${fmtDate(selection.expiry)}${
                  lotSize ? ` · lot ${lotSize}` : ' · lot size unknown'
                }`
              : 'Pick a contract from the chain'}
          </p>
        </div>
        <button
          type="button"
          className={cx(s.action, showCosts && s.actionPrimary)}
          onClick={() => setShowCosts((on) => !on)}
        >
          Charges
        </button>
      </div>

      <div className={s.panelBody}>
        {!selection ? (
          <p className={s.empty}>
            Click a premium in the option chain to plan a long position on that contract.
          </p>
        ) : (
          <>
            <div className={s.formGrid}>
              <NumberField
                label="Entry premium"
                value={inputs.entry}
                onChange={(entry) => set({ entry })}
                invalid={errorsFor('entryPremium').length > 0}
              />
              <NumberField
                label="Stop premium"
                value={inputs.stop}
                onChange={(stop) => set({ stop })}
                invalid={errorsFor('stopPremium').length > 0}
              />
              <NumberField
                label="Target premium"
                value={inputs.target}
                onChange={(target) => set({ target })}
                invalid={errorsFor('targetPremium').length > 0}
              />
              <NumberField
                label="Lots"
                value={inputs.lots}
                onChange={(lots) => set({ lots })}
                step={1}
                min={1}
                invalid={errorsFor('lots').length > 0}
              />
              <NumberField
                label="Capital"
                value={inputs.capital}
                onChange={(capital) => set({ capital })}
                step={1000}
                invalid={errorsFor('capital').length > 0}
              />
              <NumberField
                label="Risk per trade"
                value={inputs.riskPercent}
                onChange={(riskPercent) => set({ riskPercent })}
                step={0.25}
                suffix="%"
                invalid={errorsFor('riskPercent').length > 0}
              />
              <NumberField
                label="Max daily loss"
                value={inputs.maxDailyLoss}
                onChange={(maxDailyLoss) => set({ maxDailyLoss })}
                step={500}
              />
              <NumberField
                label="Lost so far today"
                value={inputs.lossSoFarToday}
                onChange={(lossSoFarToday) => set({ lossSoFarToday })}
                step={500}
              />
            </div>

            {showCosts ? (
              <>
                <p
                  className={s.panelSub}
                  style={{ margin: 'var(--cn-space-3) 0 var(--cn-space-2)' }}
                >
                  Your broker&apos;s rates. Nothing is pre-filled — every broker and plan differs,
                  and a default schedule presented as &ldquo;estimated charges&rdquo; is a number
                  you would plan around.
                </p>
                <div className={s.formGrid}>
                  <NumberField
                    label="Brokerage / order"
                    value={costs.brokeragePerOrder}
                    onChange={(brokeragePerOrder) => onCosts({ ...costs, brokeragePerOrder })}
                    step={1}
                  />
                  <NumberField
                    label="STT on sell"
                    value={costs.sttPercentOnSell}
                    onChange={(sttPercentOnSell) => onCosts({ ...costs, sttPercentOnSell })}
                    step={0.001}
                    suffix="%"
                  />
                  <NumberField
                    label="Exchange charges"
                    value={costs.exchangePercent}
                    onChange={(exchangePercent) => onCosts({ ...costs, exchangePercent })}
                    step={0.0001}
                    suffix="%"
                  />
                  <NumberField
                    label="SEBI fee"
                    value={costs.sebiPercent}
                    onChange={(sebiPercent) => onCosts({ ...costs, sebiPercent })}
                    step={0.0001}
                    suffix="%"
                  />
                  <NumberField
                    label="Stamp duty on buy"
                    value={costs.stampPercentOnBuy}
                    onChange={(stampPercentOnBuy) => onCosts({ ...costs, stampPercentOnBuy })}
                    step={0.0001}
                    suffix="%"
                  />
                  <NumberField
                    label="GST"
                    value={costs.gstPercent}
                    onChange={(gstPercent) => onCosts({ ...costs, gstPercent })}
                    step={1}
                    suffix="%"
                  />
                  <NumberField
                    label="Slippage / unit"
                    value={costs.slippagePerUnit}
                    onChange={(slippagePerUnit) => onCosts({ ...costs, slippagePerUnit })}
                    step={0.05}
                  />
                </div>
              </>
            ) : null}

            {result && result.issues.length > 0 ? (
              <ul
                className={cx(s.notice, result.valid ? s.noticeWarn : s.noticeDanger)}
                style={{ marginTop: 'var(--cn-space-3)', display: 'block', paddingLeft: '1.5rem' }}
              >
                {result.issues.map((issue) => (
                  <li key={`${issue.field}-${issue.message}`}>{issue.message}</li>
                ))}
              </ul>
            ) : null}

            {result ? (
              <>
                <dl className={s.readout}>
                  <div>
                    <dt className={s.readoutKey}>Risk per lot</dt>
                    <dd className={cx(s.readoutValue, s.down)}>{fmtRupees(result.riskPerLot)}</dd>
                  </div>
                  <div>
                    <dt className={s.readoutKey}>Planned risk</dt>
                    <dd className={cx(s.readoutValue, s.down)}>{fmtRupees(result.plannedRisk)}</dd>
                  </div>
                  <div>
                    <dt className={s.readoutKey}>Risk budget</dt>
                    <dd className={s.readoutValue}>{fmtRupees(result.riskBudget)}</dd>
                  </div>
                  <div>
                    <dt className={s.readoutKey}>Lots the budget allows</dt>
                    <dd
                      className={cx(
                        s.readoutValue,
                        result.maxLots < inputs.lots ? s.warn : undefined
                      )}
                    >
                      {result.maxLots}
                    </dd>
                  </div>
                  <div>
                    <dt className={s.readoutKey}>Reward at target</dt>
                    <dd className={cx(s.readoutValue, s.up)}>{fmtRupees(result.plannedReward)}</dd>
                  </div>
                  <div>
                    <dt className={s.readoutKey}>Reward : risk</dt>
                    <dd className={s.readoutValue}>
                      {result.plannedRisk > 0
                        ? `${(result.plannedReward / result.plannedRisk).toFixed(2)} : 1`
                        : EMPTY}
                    </dd>
                  </div>
                  <div>
                    <dt className={s.readoutKey}>Premium outlay</dt>
                    <dd className={s.readoutValue}>{fmtRupees(result.premiumOutlay)}</dd>
                  </div>
                  <div>
                    <dt className={s.readoutKey}>Breakeven at expiry</dt>
                    <dd className={cx(s.readoutValue, 'cn-numeric')}>
                      {fmtPrice(result.breakevenLevel)}
                    </dd>
                  </div>
                  <div>
                    <dt className={s.readoutKey}>
                      {result.costsExcluded ? 'Charges (not set)' : 'Charges round trip'}
                    </dt>
                    <dd className={s.readoutValue}>
                      {result.costsExcluded ? EMPTY : fmtRupeesPrecise(result.estimatedCosts)}
                    </dd>
                  </div>
                  <div>
                    <dt className={s.readoutKey}>Net at target</dt>
                    <dd className={cx(s.readoutValue, s.up)}>{fmtRupees(result.netAtTarget)}</dd>
                  </div>
                  <div>
                    <dt className={s.readoutKey}>Net at stop</dt>
                    <dd className={cx(s.readoutValue, s.down)}>{fmtRupees(result.netAtStop)}</dd>
                  </div>
                  <div>
                    <dt className={s.readoutKey}>Daily risk left</dt>
                    <dd
                      className={cx(
                        s.readoutValue,
                        result.remainingDailyRisk != null && result.remainingDailyRisk < 0
                          ? s.down
                          : undefined
                      )}
                    >
                      {result.remainingDailyRisk != null
                        ? fmtRupees(result.remainingDailyRisk)
                        : EMPTY}
                    </dd>
                  </div>
                </dl>

                {result.remainingDailyRisk != null && result.remainingDailyRisk < 0 ? (
                  <p
                    className={cx(s.notice, s.noticeDanger)}
                    style={{ marginTop: 'var(--cn-space-3)' }}
                  >
                    <span>
                      This trade would take you past your daily loss limit if it hits the stop.
                    </span>
                  </p>
                ) : null}

                {result.costsExcluded ? (
                  <p
                    className={cx(s.notice, s.noticeWarn)}
                    style={{ marginTop: 'var(--cn-space-2)' }}
                  >
                    <span>
                      Charges and slippage are excluded — not zero. Open Charges and enter your
                      broker&apos;s rates for a net figure that means anything.
                    </span>
                  </p>
                ) : null}

                <p className={s.notice} style={{ marginTop: 'var(--cn-space-2)' }}>
                  <span>
                    <strong>The stop is a price you intend, not one you are guaranteed.</strong> A
                    gap through it fills where the market is; a wide spread or a thin book fills
                    worse than the mid; an order sent into the open may not fill at all. Size on the
                    assumption that the loss can exceed the planned figure.
                  </span>
                </p>

                <button
                  type="button"
                  className={cx(s.action, s.actionPrimary)}
                  style={{ marginTop: 'var(--cn-space-3)' }}
                  onClick={onJournal}
                  disabled={!result.valid}
                >
                  Save this plan to the journal
                </button>
              </>
            ) : null}
          </>
        )}
      </div>
    </section>
  );
}
