import { useMemo, useState } from 'react';
import Select from '$shared/ui/Select';
import { cx } from '$shared/ui/cx';
import { EMPTY, fmtDate, fmtPrice, fmtRupees } from '../calc/format';
import type { JournalEntry } from '../store';
import s from '../stock-watch.module.css';

interface Props {
  symbol: string;
  entries: JournalEntry[];
  onRemove: (id: string) => void;
  onUpdate: (entry: JournalEntry) => void;
}

type Scope = 'this' | 'all';

/**
 * A record of what was planned and what happened.
 *
 * **These are your entries, not your fills.** Nothing here comes from a
 * broker: every number was typed on this page or carried over from the
 * planner, and it lives in this browser's local storage — not in an account,
 * not synced, not backed up. The panel says so at the top rather than in small
 * print, because a journal that reads like a contract note is one somebody
 * eventually reconciles their taxes against.
 *
 * The context block on each row — spot, basis, ATM IV, PCR, structure — is
 * captured at entry. Reconstructing what the book looked like at 10:42 after
 * the fact is impossible, which is the whole argument for recording it now.
 */
export default function JournalPanel({ symbol, entries, onRemove, onUpdate }: Props) {
  const [scope, setScope] = useState<Scope>('this');
  const [setupFilter, setSetupFilter] = useState('all');

  const scoped = useMemo(
    () => (scope === 'this' ? entries.filter((entry) => entry.symbol === symbol) : entries),
    [entries, scope, symbol]
  );

  const setups = useMemo(() => {
    const names = new Set(scoped.map((entry) => entry.setup).filter(Boolean));
    return ['all', ...names];
  }, [scoped]);

  const rows = useMemo(
    () => (setupFilter === 'all' ? scoped : scoped.filter((entry) => entry.setup === setupFilter)),
    [scoped, setupFilter]
  );

  const summary = useMemo(() => {
    const closed = rows.filter((entry) => entry.netPnl != null);
    const net = closed.reduce((total, entry) => total + (entry.netPnl ?? 0), 0);
    const wins = closed.filter((entry) => (entry.netPnl ?? 0) > 0).length;
    return { closed: closed.length, open: rows.length - closed.length, net, wins };
  }, [rows]);

  return (
    <section className={s.panel}>
      <div className={s.panelHead}>
        <div>
          <h2 className={s.panelTitle}>Trade journal</h2>
          <p className={s.panelSub}>
            {rows.length} entr{rows.length === 1 ? 'y' : 'ies'} · {summary.closed} closed ·{' '}
            {summary.wins}/{summary.closed || 0} positive · net {fmtRupees(summary.net)}
          </p>
        </div>
        <div className={s.panelActions}>
          <Select
            value={scope}
            options={[
              { value: 'this' as const, label: `${symbol} only` },
              { value: 'all' as const, label: 'All symbols' }
            ]}
            onChange={setScope}
            ariaLabel="Journal scope"
            size="sm"
          />
          <Select
            value={setupFilter}
            options={setups.map((name) => ({
              value: name,
              label: name === 'all' ? 'All setups' : name
            }))}
            onChange={setSetupFilter}
            ariaLabel="Setup filter"
            size="sm"
            align="right"
          />
        </div>
      </div>

      <div className={s.panelBodyFlush}>
        <p className={cx(s.notice, s.noticeWarn)} style={{ margin: 'var(--cn-space-3)' }}>
          <span>
            <strong>Manually entered, stored in this browser only.</strong> Nothing here comes from
            a broker account. It is not synced between devices, it is not backed up, and clearing
            site data deletes it. Do not treat it as a statement of executed trades.
          </span>
        </p>

        {rows.length === 0 ? (
          <p className={s.empty}>
            No entries yet. Plan a trade in the planner and save it here, then fill in the exit when
            you are out.
          </p>
        ) : (
          <div className={s.tableScroll}>
            <table className={s.table}>
              <thead>
                <tr>
                  <th className={s.left}>Date</th>
                  <th className={s.left}>Contract</th>
                  <th>Lots</th>
                  <th>Entry</th>
                  <th>Exit</th>
                  <th>Stop</th>
                  <th>Target</th>
                  <th>Net P&amp;L</th>
                  <th className={s.left}>Setup</th>
                  <th className={s.left}>Context at entry</th>
                  <th className={s.left}>Exit reason</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {rows.map((entry) => (
                  <tr key={entry.id}>
                    <td className={s.left}>{fmtDate(entry.tradeDate)}</td>
                    <td className={cx(s.left, 'cn-numeric')}>
                      {entry.symbol} {fmtPrice(entry.strike)} {entry.type}
                      <span className={s.muted}> · {fmtDate(entry.expiry)}</span>
                    </td>
                    <td>{entry.lots}</td>
                    <td className="cn-numeric">{fmtPrice(entry.entry)}</td>
                    <td>
                      <input
                        className="cn-numeric"
                        type="number"
                        step={0.05}
                        value={entry.exit ?? ''}
                        placeholder="—"
                        style={{
                          width: '5rem',
                          background: 'transparent',
                          border: '1px solid var(--cn-border)',
                          borderRadius: 'var(--cn-radius-sm)',
                          color: 'var(--cn-text)',
                          padding: '0.125rem 0.25rem',
                          textAlign: 'right'
                        }}
                        onChange={(event) => {
                          const exit = Number(event.target.value);
                          const gross = Number.isFinite(exit)
                            ? (exit - entry.entry) * entry.lotSize * entry.lots
                            : undefined;
                          onUpdate({
                            ...entry,
                            exit: Number.isFinite(exit) ? exit : undefined,
                            grossPnl: gross,
                            netPnl: gross != null ? gross - (entry.charges ?? 0) : undefined
                          });
                        }}
                      />
                    </td>
                    <td className="cn-numeric">{fmtPrice(entry.stop)}</td>
                    <td className="cn-numeric">{fmtPrice(entry.target)}</td>
                    <td
                      className={cx(
                        'cn-numeric',
                        entry.netPnl != null ? (entry.netPnl >= 0 ? s.up : s.down) : undefined
                      )}
                    >
                      {entry.netPnl != null ? fmtRupees(entry.netPnl) : EMPTY}
                    </td>
                    <td className={s.left}>{entry.setup || EMPTY}</td>
                    <td className={cx(s.left, s.muted)} style={{ whiteSpace: 'normal' }}>
                      {[
                        entry.context.spot != null ? `spot ${fmtPrice(entry.context.spot)}` : null,
                        entry.context.atmIv != null
                          ? `IV ${entry.context.atmIv.toFixed(1)}%`
                          : null,
                        entry.context.pcrOi != null
                          ? `PCR ${entry.context.pcrOi.toFixed(2)}`
                          : null,
                        entry.context.futuresBasisPercent != null
                          ? `basis ${entry.context.futuresBasisPercent.toFixed(2)}%`
                          : null,
                        entry.context.structure
                      ]
                        .filter(Boolean)
                        .join(' · ') || EMPTY}
                    </td>
                    <td className={s.left}>
                      <input
                        type="text"
                        value={entry.exitReason}
                        placeholder="why you got out"
                        style={{
                          width: '10rem',
                          background: 'transparent',
                          border: '1px solid var(--cn-border)',
                          borderRadius: 'var(--cn-radius-sm)',
                          color: 'var(--cn-text)',
                          padding: '0.125rem 0.25rem'
                        }}
                        onChange={(event) => onUpdate({ ...entry, exitReason: event.target.value })}
                      />
                    </td>
                    <td>
                      <button
                        type="button"
                        className={cx(s.action, s.actionDanger)}
                        onClick={() => onRemove(entry.id)}
                        aria-label="Delete entry"
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
      </div>
    </section>
  );
}
