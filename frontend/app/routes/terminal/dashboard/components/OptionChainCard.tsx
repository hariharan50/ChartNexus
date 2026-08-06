import { useMemo, useState } from 'react';
import {
  direction,
  formatInt,
  formatPercent,
  formatPrice,
  formatSignedInt
} from '$shared/formatting/numbers';
import { cx } from '$shared/ui/cx';
import IconChart from '$shared/ui/icons/IconChart';
import { buildUpTone, type OptionRow } from '../dashboard-data';
import s from './OptionChainCard.module.css';
import Panel from './Panel';
import Pill from './Pill';

interface Props {
  rows: OptionRow[];
  loading?: boolean;
}

/** Strike-count choices for the header toggle; 6 keeps the default compact. */
const STRIKE_CHOICES = [6, 10, 20] as const;

export default function OptionChainCard({ rows, loading = false }: Props) {
  const [visibleStrikes, setVisibleStrikes] = useState<number>(STRIKE_CHOICES[0]);

  /**
   * Rows arrive sorted by strike (PE then CE per strike). Show only a window of
   * `visibleStrikes` strikes centred on the ATM strike, so the default view is
   * tight and the toggle expands it symmetrically around spot.
   */
  const visibleRows = useMemo(() => {
    // Group rows into strikes, preserving order.
    const strikes: OptionRow[][] = [];
    let currentStrike: number | null = null;
    for (const row of rows) {
      if (row.strike !== currentStrike) {
        currentStrike = row.strike;
        strikes.push([]);
      }
      strikes[strikes.length - 1]!.push(row);
    }

    if (strikes.length <= visibleStrikes) return rows;

    const atmIndex = strikes.findIndex((group) => group.some((r) => r.atm));
    const centre = atmIndex === -1 ? Math.floor(strikes.length / 2) : atmIndex;
    let start = centre - Math.floor(visibleStrikes / 2);
    start = Math.max(0, Math.min(start, strikes.length - visibleStrikes));

    return strikes.slice(start, start + visibleStrikes).flat();
  }, [rows, visibleStrikes]);

  return (
    <Panel
      title="Option Chain"
      subtitle="Top strikes around spot"
      icon={<IconChart />}
      actions={
        <div className={s.strikeToggle} role="group" aria-label="Strikes to show">
          {STRIKE_CHOICES.map((choice) => (
            <button
              key={choice}
              type="button"
              className={cx(visibleStrikes === choice && s.active)}
              aria-pressed={visibleStrikes === choice}
              onClick={() => setVisibleStrikes(choice)}
            >
              {choice}
            </button>
          ))}
        </div>
      }
    >
      <div className={s.scroll}>
        <table>
          <thead>
            <tr>
              <th className={s.strike}>Strike</th>
              <th>Type</th>
              <th className={s.num}>OI</th>
              <th className={s.num}>OI Chg</th>
              <th className={s.num}>LTP</th>
              <th className={s.num}>IV</th>
              <th>Build-up</th>
            </tr>
          </thead>
          <tbody>
            {visibleRows.map((row) => {
              const dir = direction(row.oiChange);
              return (
                <tr key={row.strike + row.type} className={cx(row.atm && s.atm)}>
                  <td className={s.strike}>
                    <span className="mc-numeric">{formatInt(row.strike)}</span>
                    {row.atm ? (
                      <Pill tone="accent" subtle>
                        ATM
                      </Pill>
                    ) : null}
                  </td>
                  <td>
                    <Pill tone={row.type === 'CE' ? 'bullish' : 'bearish'}>{row.type}</Pill>
                  </td>
                  <td className={`${s.num} mc-numeric`}>{formatInt(row.oi)}</td>
                  <td
                    className={cx(
                      s.num,
                      'mc-numeric',
                      dir === 'up' && s.up,
                      dir === 'down' && s.down
                    )}
                  >
                    {formatSignedInt(row.oiChange)}
                  </td>
                  <td className={`${s.num} mc-numeric`}>{formatPrice(row.ltp)}</td>
                  <td className={cx(s.num, 'mc-numeric', s.muted)}>
                    {Number.isNaN(row.iv) ? '—' : formatPercent(row.iv)}
                  </td>
                  <td>
                    <Pill tone={buildUpTone(row.buildUp)}>{row.buildUp}</Pill>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {rows.length === 0 ? (
          <p className={s.empty}>{loading ? 'Loading option chain…' : 'No strikes available.'}</p>
        ) : null}
      </div>
    </Panel>
  );
}
