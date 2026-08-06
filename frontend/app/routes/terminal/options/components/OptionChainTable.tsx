import { useMemo, useState } from 'react';
import { buildUpTone, type BuildUp, type OptionRow } from '$contexts/market-data/view-models';
import {
  direction,
  formatInt,
  formatPercent,
  formatPrice,
  formatSignedInt
} from '$shared/formatting/numbers';
import { cx } from '$shared/ui/cx';
import IconChart from '$shared/ui/icons/IconChart';
import Panel from '../../dashboard/components/Panel';
import Pill from '../../dashboard/components/Pill';
import s from './OptionChainTable.module.css';

interface Props {
  rows: OptionRow[];
  loading?: boolean;
}

type Filter = 'all' | 'CE' | 'PE';

const FILTERS: { key: Filter; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'CE', label: 'CE' },
  { key: 'PE', label: 'PE' }
];

const LEGEND: BuildUp[] = ['Long Build-up', 'Short Build-up', 'Long Unwinding', 'Short Covering'];

export default function OptionChainTable({ rows, loading = false }: Props) {
  const [filter, setFilter] = useState<Filter>('all');

  // The chain arrives as PE-then-CE per strike; this page shows CE first, grouped
  // by strike ascending. Filtering to a single leg keeps that ordering.
  const visibleRows = useMemo(
    () =>
      [...rows]
        .filter((row) => filter === 'all' || row.type === filter)
        .sort((a, b) => a.strike - b.strike || (a.type === 'CE' ? -1 : 1)),
    [rows, filter]
  );

  return (
    <Panel
      title="Option Chain"
      subtitle="Colour-coded by OI build-up"
      icon={<IconChart />}
      actions={
        <div className={s.filter} role="group" aria-label="Filter option type">
          {FILTERS.map((choice) => (
            <button
              key={choice.key}
              type="button"
              className={cx(filter === choice.key && s.active)}
              aria-pressed={filter === choice.key}
              onClick={() => setFilter(choice.key)}
            >
              {choice.label}
            </button>
          ))}
        </div>
      }
    >
      <div className={s.legend} aria-hidden="true">
        {LEGEND.map((tag) => (
          <span className={cx(s.legendItem, s[buildUpTone(tag)])} key={tag}>
            <span className={s.dot} />
            {tag}
          </span>
        ))}
      </div>

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
                  <td className={cx(s.num, 'mc-numeric')}>{formatInt(row.oi)}</td>
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
                  <td className={cx(s.num, 'mc-numeric')}>{formatPrice(row.ltp)}</td>
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
        {visibleRows.length === 0 ? (
          <p className={s.empty}>{loading ? 'Loading option chain…' : 'No strikes available.'}</p>
        ) : null}
      </div>
    </Panel>
  );
}
