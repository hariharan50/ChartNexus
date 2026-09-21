import { useMemo } from 'react';
import type { Instrument } from '$contexts/instrument-catalog/types';
import type { FuturesRow } from '$contexts/futures-analytics/types';
import { cx } from '$shared/ui/cx';
import { advanceDecline, fmtPercent, sectorPerformance } from '../stocks-data';
import s from './SidePanels.module.css';

/**
 * The rail: how broad the move is, and where it is concentrated.
 *
 * Both panels are derived from the rows already on screen rather than fetched —
 * there is no second request here, and nothing can disagree with the table
 * beside it.
 */
interface Props {
  /** Always the full board, never the filtered view: breadth is a statement
   *  about the market, and narrowing it to one sector would make the
   *  Advance/Decline line meaningless. */
  rows: FuturesRow[];
  instruments: Instrument[];
  sector: string;
  onSector: (value: string) => void;
}

export default function SidePanels({ rows, instruments, sector, onSector }: Props) {
  const membership = useMemo(() => {
    const byIndex = new Map<string, Set<string>>();
    for (const entry of instruments) {
      // An API predating the field sends no `indices` at all.
      for (const name of entry.indices ?? []) {
        const members = byIndex.get(name) ?? new Set<string>();
        members.add(entry.symbol);
        byIndex.set(name, members);
      }
    }
    return byIndex;
  }, [instruments]);

  const categories = useMemo(() => {
    const out = [advanceDecline('FNO Stocks', rows)];
    // Only indices we actually hold membership for. A row reading 0 / 0
    // because the curated table is missing would look like a dead market.
    for (const [name, label] of [
      ['NIFTY50', 'NIFTY'],
      ['BANKNIFTY', 'BANKNIFTY']
    ] as const) {
      const members = membership.get(name);
      if (!members?.size) continue;
      out.push(
        advanceDecline(
          label,
          rows.filter((row) => members.has(row.symbol))
        )
      );
    }
    return out;
  }, [rows, membership]);

  const sectors = useMemo(() => sectorPerformance(rows), [rows]);

  return (
    <aside className={s.rail}>
      <section className={s.panel}>
        <header className={s.head}>
          <span>Category</span>
          <span className={s.right}>Adv / Dec</span>
        </header>
        <ul className={s.list}>
          {categories.map((entry) => (
            <li key={entry.label} className={s.row}>
              <span className={s.name}>{entry.label}</span>
              <span className={s.right}>
                <span className={s.up}>{entry.advances}</span>
                <span className={s.slash}>/</span>
                <span className={s.down}>{entry.declines}</span>
              </span>
            </li>
          ))}
        </ul>
      </section>

      {sectors.length > 0 ? (
        <section className={cx(s.panel, s.scrollPanel)}>
          <header className={s.head}>
            <span>Sector</span>
            <span className={s.right}>Price %</span>
          </header>
          <ul className={s.list}>
            {sectors.map((entry) => {
              const selected = entry.sector === sector;
              return (
                <li key={entry.sector}>
                  <button
                    type="button"
                    className={cx(s.row, s.rowBtn, selected && s.selected)}
                    aria-pressed={selected}
                    title={`${entry.count} contracts`}
                    onClick={() => onSector(selected ? '' : entry.sector)}
                  >
                    <span className={s.name}>{entry.sector}</span>
                    <span className={cx(s.right, entry.changePercent >= 0 ? s.up : s.down)}>
                      {fmtPercent(entry.changePercent)}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        </section>
      ) : null}
    </aside>
  );
}
