import { useMemo, useState } from 'react';
import Select from '$shared/ui/Select';
import { cx } from '$shared/ui/cx';
import type { EnrichedChain } from '../calc/chain';
import { EMPTY, fmtDate, fmtIndian, fmtPrice, fmtRupees } from '../calc/format';
import { type ComparisonInput, compare } from '../calc/plan';
import s from '../stock-watch.module.css';

type SortKey =
  | 'strike'
  | 'premiumPerLot'
  | 'spreadPercent'
  | 'volume'
  | 'oi'
  | 'iv'
  | 'delta'
  | 'thetaPercentPerDay'
  | 'breakevenLevel';

const SORTS: { value: SortKey; label: string }[] = [
  { value: 'strike', label: 'Strike' },
  { value: 'premiumPerLot', label: 'Premium per lot' },
  { value: 'spreadPercent', label: 'Spread %' },
  { value: 'volume', label: 'Volume' },
  { value: 'oi', label: 'Open interest' },
  { value: 'iv', label: 'Implied volatility' },
  { value: 'delta', label: 'Delta' },
  { value: 'thetaPercentPerDay', label: 'Theta drag' },
  { value: 'breakevenLevel', label: 'Breakeven' }
];

interface Props {
  chain: EnrichedChain;
  /** `strike:TYPE` keys the reader added from the chain. */
  shortlist: Set<string>;
  onClear: () => void;
  onRemove: (key: string) => void;
}

/**
 * Side-by-side comparison of the contracts the reader shortlisted.
 *
 * **No "best" column, and the sort is the reader's.** The highest volume, the
 * tightest spread and the cheapest premium are three different contracts most
 * days, and which one is right depends on the trade: a scalp wants the spread,
 * an overnight hold wants the theta, a small account wants the outlay. The
 * table ranks what it is asked to rank and makes no recommendation.
 */
export default function ContractCompare({ chain, shortlist, onClear, onRemove }: Props) {
  const [sort, setSort] = useState<SortKey>('strike');

  const rows = useMemo(() => {
    const inputs: (ComparisonInput & { key: string })[] = [];
    for (const key of shortlist) {
      const [strikeText, type] = key.split(':');
      const strike = Number(strikeText);
      const row = chain.rows.find((candidate) => candidate.strike === strike);
      const leg = type === 'CE' ? row?.ce : row?.pe;
      if (!row || !leg) continue;

      const input: ComparisonInput & { key: string } = {
        key,
        strike,
        type: leg.type,
        expiry: chain.expiry,
        ltp: leg.ltp,
        volume: leg.volume,
        oi: leg.oi,
        lotSize: chain.lotSize ?? 0
      };
      if (leg.bid != null) input.bid = leg.bid;
      if (leg.ask != null) input.ask = leg.ask;
      if (leg.iv != null) input.iv = leg.iv;
      if (leg.modelGreeks) {
        input.delta = leg.modelGreeks.delta;
        input.gamma = leg.modelGreeks.gamma;
        input.theta = leg.modelGreeks.theta;
        input.vega = leg.modelGreeks.vega;
      } else if (leg.quotedDelta != null) {
        input.delta = leg.quotedDelta;
      }
      inputs.push(input);
    }

    const compared = compare(inputs).map((row, index) => ({
      ...row,
      key: inputs[index]?.key ?? `${row.strike}:${row.type}`,
      liquidity: chain.rows.find((candidate) => candidate.strike === row.strike)?.[
        row.type === 'CE' ? 'ce' : 'pe'
      ]?.liquidity
    }));

    const read = (row: (typeof compared)[number]): number => {
      const value = row[sort as keyof typeof row];
      return typeof value === 'number' ? value : Number.NEGATIVE_INFINITY;
    };
    return sort === 'strike'
      ? [...compared].sort((a, b) => a.strike - b.strike)
      : [...compared].sort((a, b) => read(b) - read(a));
  }, [chain, shortlist, sort]);

  return (
    <section className={s.panel}>
      <div className={s.panelHead}>
        <div>
          <h2 className={s.panelTitle}>Contract comparison</h2>
          <p className={s.panelSub}>
            {rows.length === 0
              ? 'Click a build-up chip in the chain to shortlist a contract'
              : `${rows.length} shortlisted · ${fmtDate(chain.expiry)}`}
          </p>
        </div>
        <div className={s.panelActions}>
          <Select value={sort} options={SORTS} onChange={setSort} ariaLabel="Sort by" size="sm" />
          <button type="button" className={s.action} onClick={onClear} disabled={rows.length === 0}>
            Clear
          </button>
        </div>
      </div>

      <div className={s.panelBodyFlush}>
        {rows.length === 0 ? (
          <p className={s.empty}>
            Nothing shortlisted yet. In the option chain, click the build-up chip on any leg to add
            it here.
          </p>
        ) : (
          <div className={s.tableScroll}>
            <table className={s.table}>
              <thead>
                <tr>
                  <th className={s.left}>Contract</th>
                  <th>LTP</th>
                  <th>Per lot</th>
                  <th>Spread</th>
                  <th>Spread %</th>
                  <th>Volume</th>
                  <th>OI</th>
                  <th>IV</th>
                  <th>δ</th>
                  <th>θ/day</th>
                  <th>θ as % of premium</th>
                  <th>Breakeven</th>
                  <th className={s.left}>Liquidity</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.key}>
                    <td className={cx(s.left, 'cn-numeric')}>
                      {fmtPrice(row.strike)} {row.type}
                    </td>
                    <td className="cn-numeric">{fmtPrice(row.ltp)}</td>
                    <td className="cn-numeric">
                      {row.lotSize > 0 ? fmtRupees(row.premiumPerLot) : EMPTY}
                    </td>
                    <td className="cn-numeric">{fmtPrice(row.spread)}</td>
                    <td
                      className={cx(
                        'cn-numeric',
                        row.spreadPercent != null && row.spreadPercent >= 6 ? s.danger : undefined
                      )}
                    >
                      {row.spreadPercent != null ? `${row.spreadPercent.toFixed(1)}%` : EMPTY}
                    </td>
                    <td>{fmtIndian(row.volume)}</td>
                    <td>{fmtIndian(row.oi)}</td>
                    <td>{row.iv != null ? `${row.iv.toFixed(1)}%` : EMPTY}</td>
                    <td>{row.delta != null ? row.delta.toFixed(3) : EMPTY}</td>
                    <td className={s.down}>{row.theta != null ? row.theta.toFixed(2) : EMPTY}</td>
                    <td className={s.down}>
                      {row.thetaPercentPerDay != null
                        ? `${row.thetaPercentPerDay.toFixed(2)}%`
                        : EMPTY}
                    </td>
                    <td className="cn-numeric">{fmtPrice(row.breakevenLevel)}</td>
                    <td className={s.left}>
                      <span
                        className={cx(
                          s.chip,
                          row.liquidity?.grade === 'illiquid'
                            ? s.chipDown
                            : row.liquidity?.grade === 'thin'
                              ? s.chipWarn
                              : s.chipNeutral
                        )}
                        title={row.liquidity?.reasons.join('\n')}
                      >
                        {row.liquidity?.grade ?? 'unknown'}
                      </span>
                    </td>
                    <td>
                      <button
                        type="button"
                        className={cx(s.action, s.actionDanger)}
                        onClick={() => onRemove(row.key)}
                        aria-label={`Remove ${row.strike} ${row.type}`}
                      >
                        ×
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <p className={s.notice} style={{ margin: 'var(--cn-space-3)' }}>
          <span>
            Breakeven is at expiry for a long position and excludes charges — add your round-trip
            cost in the planner to see the level you actually need. Greeks are model values; theta
            as a share of premium is the clearest read of how fast an unmoved position bleeds.
            Nothing here ranks a contract as the right one: that depends on the trade, not on the
            chain.
          </span>
        </p>
      </div>
    </section>
  );
}
