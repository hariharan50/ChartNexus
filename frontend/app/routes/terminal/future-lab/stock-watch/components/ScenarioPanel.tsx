import { useMemo, useState } from 'react';
import { cx } from '$shared/ui/cx';
import { EMPTY, fmtPrice, fmtRupees } from '../calc/format';
import { DEFAULT_MOVES, type ScenarioInput, scenarioRow } from '../calc/plan';
import type { Selection } from './TradePlanner';
import s from '../stock-watch.module.css';

interface Props {
  selection?: Selection | undefined;
  spot?: number | undefined;
  daysToExpiry: number;
  entryPremium: number;
  lots: number;
}

/**
 * What the contract is worth if the underlying, volatility or the calendar
 * move — the three things that actually change an option's price.
 *
 * Every cell is a Black-Scholes value under stated assumptions, not a quote.
 * Nothing can be filled at these prices, and the expiry row is the payoff
 * rather than a model value: at zero days a model with a tiny time stub
 * returns a few paise of optimism on a contract that is worthless, and a
 * planner that shows that is the one that gets believed on expiry afternoon.
 */
export default function ScenarioPanel({
  selection,
  spot,
  daysToExpiry,
  entryPremium,
  lots
}: Props) {
  const [ivChange, setIvChange] = useState(0);
  const [daysElapsed, setDaysElapsed] = useState(0);

  const iv = selection?.leg.iv;

  const input = useMemo<ScenarioInput | undefined>(() => {
    if (!selection || spot == null || iv == null || !(selection.lotSize ?? 0)) return undefined;
    return {
      type: selection.type,
      strike: selection.strike,
      spot,
      iv,
      days: daysToExpiry,
      entryPremium,
      lotSize: selection.lotSize ?? 0,
      lots
    };
  }, [selection, spot, iv, daysToExpiry, entryPremium, lots]);

  const cells = useMemo(
    () => (input ? scenarioRow(input, DEFAULT_MOVES, { ivChange, daysElapsed }) : []),
    [input, ivChange, daysElapsed]
  );

  return (
    <section className={s.panel}>
      <div className={s.panelHead}>
        <div>
          <h2 className={s.panelTitle}>Scenario analysis</h2>
          <p className={s.panelSub}>
            {selection
              ? `Long ${fmtPrice(selection.strike)} ${selection.type} · entry ${fmtPrice(entryPremium)} · ${lots} lot${lots === 1 ? '' : 's'}`
              : 'Pick a contract from the chain'}
          </p>
        </div>
      </div>

      <div className={s.panelBody}>
        {!selection ? (
          <p className={s.empty}>Select a contract to model it.</p>
        ) : iv == null ? (
          <p className={s.empty}>
            This leg has no implied volatility, so there is nothing to reprice it with. Scenarios
            need a volatility input and will not invent one.
          </p>
        ) : !selection.lotSize ? (
          <p className={s.empty}>
            The catalog has no lot size for this underlying, so a per-lot figure cannot be computed.
          </p>
        ) : (
          <>
            <div className={s.formGrid}>
              <label className={s.field}>
                <span className={s.fieldLabel}>
                  IV change: {ivChange > 0 ? '+' : ''}
                  {ivChange} vol points (now {iv.toFixed(1)}%)
                </span>
                <input
                  type="range"
                  min={-15}
                  max={15}
                  step={1}
                  value={ivChange}
                  onChange={(event) => setIvChange(Number(event.target.value))}
                />
              </label>
              <label className={s.field}>
                <span className={s.fieldLabel}>
                  Days elapsed: {daysElapsed} of {daysToExpiry}
                </span>
                <input
                  type="range"
                  min={0}
                  max={Math.max(1, daysToExpiry)}
                  step={1}
                  value={Math.min(daysElapsed, daysToExpiry)}
                  onChange={(event) => setDaysElapsed(Number(event.target.value))}
                />
              </label>
            </div>

            <div className={s.tableScroll} style={{ marginTop: 'var(--cn-space-3)' }}>
              <table className={s.table}>
                <thead>
                  <tr>
                    <th className={s.left}>Underlying</th>
                    <th>Spot</th>
                    <th>Premium</th>
                    <th>P&amp;L / unit</th>
                    <th>P&amp;L / lot</th>
                    <th>P&amp;L position</th>
                    <th>δ</th>
                    <th>γ</th>
                    <th>θ</th>
                    <th>ν</th>
                  </tr>
                </thead>
                <tbody>
                  {cells.map((cell) => (
                    <tr key={cell.spotMovePercent}>
                      <td className={s.left}>
                        {cell.spotMovePercent > 0 ? '+' : ''}
                        {cell.spotMovePercent}%
                      </td>
                      <td className="cn-numeric">{fmtPrice(cell.spot)}</td>
                      <td className="cn-numeric">{fmtPrice(cell.premium)}</td>
                      <td className={cx('cn-numeric', cell.pnlPerUnit >= 0 ? s.up : s.down)}>
                        {fmtPrice(cell.pnlPerUnit)}
                      </td>
                      <td className={cx('cn-numeric', cell.pnlPerLot >= 0 ? s.up : s.down)}>
                        {fmtRupees(cell.pnlPerLot)}
                      </td>
                      <td className={cx('cn-numeric', cell.pnlPosition >= 0 ? s.up : s.down)}>
                        {fmtRupees(cell.pnlPosition)}
                      </td>
                      <td>{cell.atExpiry ? EMPTY : cell.delta.toFixed(3)}</td>
                      <td>{cell.atExpiry ? EMPTY : cell.gamma.toFixed(5)}</td>
                      <td className={s.down}>{cell.atExpiry ? EMPTY : cell.theta.toFixed(2)}</td>
                      <td>{cell.atExpiry ? EMPTY : cell.vega.toFixed(3)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <p className={s.notice} style={{ marginTop: 'var(--cn-space-3)' }}>
              <span>
                <strong>Assumptions.</strong> Black-Scholes at a 7% risk-free rate, no dividend,
                European exercise, and the implied volatility shown — held flat across strikes. NSE
                stock options are American-style, so a deep in-the-money put in particular can trade
                above these values. The{' '}
                {cells[0]?.daysLeft === 0 ? 'rows below' : 'row at 0 days left'}{' '}
                {cells.some((cell) => cell.atExpiry)
                  ? 'use the expiry payoff, not a model price. '
                  : ''}
                These are theoretical values; no order can be filled at them.
              </span>
            </p>
          </>
        )}
      </div>
    </section>
  );
}
