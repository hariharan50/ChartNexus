import { useState } from 'react';
import Select from '$shared/ui/Select';
import { cx } from '$shared/ui/cx';
import {
  ALERT_COOLDOWN_MS,
  ALERT_LABELS,
  type AlertKind,
  type AlertRule,
  type FiredAlert
} from '../store';
import { fmtIst } from '../calc/format';
import s from '../stock-watch.module.css';

/** Kinds that take no threshold — they fire on a state, not a level. */
const STATE_ONLY: AlertKind[] = ['futures_buildup', 'feed_stale', 'ban_status'];

interface Props {
  symbol: string;
  rules: AlertRule[];
  fired: FiredAlert[];
  watchlist: string[];
  onAdd: (kind: AlertKind, threshold: number) => void;
  onToggle: (id: string) => void;
  onRemove: (id: string) => void;
  onPick: (symbol: string) => void;
}

/**
 * Alerts evaluated against the data this page is already polling.
 *
 * **Browser-session alerts, not server-side ones.** They fire while this tab
 * is open and the page is polling; close it and nothing is watching. That is
 * stated plainly, because an alert you believe is running and is not is worse
 * than no alert at all — a server-side rule engine with push delivery is a
 * different feature with its own persistence and its own notification
 * transport, and this is not pretending to be it.
 *
 * Each rule has a five-minute cooldown. Without one, a price alert on a level
 * the stock is sitting on fires on every poll, fifteen seconds apart, until
 * the reader turns alerts off entirely — which costs them the one that
 * mattered.
 */
export default function AlertsPanel({
  symbol,
  rules,
  fired,
  watchlist,
  onAdd,
  onToggle,
  onRemove,
  onPick
}: Props) {
  const [kind, setKind] = useState<AlertKind>('price_above');
  const [threshold, setThreshold] = useState(0);

  const mine = rules.filter((rule) => rule.symbol === symbol);
  const needsThreshold = !STATE_ONLY.includes(kind);

  return (
    <div className={s.stack}>
      <section className={s.panel}>
        <div className={s.panelHead}>
          <div>
            <h2 className={s.panelTitle}>Alerts</h2>
            <p className={s.panelSub}>
              {mine.length} rule{mine.length === 1 ? '' : 's'} on {symbol} · evaluated on every poll
            </p>
          </div>
        </div>

        <div className={s.panelBody}>
          <p className={cx(s.notice, s.noticeWarn)}>
            <span>
              <strong>These run in this browser tab.</strong> They are checked each time the page
              polls and stop the moment you close or navigate away — there is no server watching on
              your behalf and no push notification. Each rule stays quiet for{' '}
              {ALERT_COOLDOWN_MS / 60_000} minutes after firing.
            </span>
          </p>

          <div className={s.formGrid} style={{ marginTop: 'var(--cn-space-3)' }}>
            {/* A div, not a label: `Select` renders a button-and-listbox,
                not a native control, so a wrapping label would have nothing to
                associate with. `ariaLabel` on the control is what names it. */}
            <div className={s.field}>
              <span className={s.fieldLabel}>Condition</span>
              <Select
                value={kind}
                options={(Object.keys(ALERT_LABELS) as AlertKind[]).map((value) => ({
                  value,
                  label: ALERT_LABELS[value]
                }))}
                onChange={setKind}
                ariaLabel="Alert condition"
                size="sm"
              />
            </div>
            {needsThreshold ? (
              <label className={s.field}>
                <span className={s.fieldLabel}>Threshold</span>
                <input
                  type="number"
                  step={0.05}
                  value={Number.isFinite(threshold) ? threshold : ''}
                  onChange={(event) => setThreshold(Number(event.target.value))}
                />
              </label>
            ) : null}
            <div className={s.field}>
              <span className={s.fieldLabel}>&nbsp;</span>
              <button
                type="button"
                className={cx(s.action, s.actionPrimary)}
                disabled={needsThreshold && !(threshold > 0)}
                onClick={() => onAdd(kind, threshold)}
              >
                Add alert
              </button>
            </div>
          </div>

          {mine.length === 0 ? (
            <p className={s.empty}>No rules on {symbol} yet.</p>
          ) : (
            <div className={s.tableScroll} style={{ marginTop: 'var(--cn-space-3)' }}>
              <table className={s.table}>
                <thead>
                  <tr>
                    <th className={s.left}>Condition</th>
                    <th>Threshold</th>
                    <th>Last fired</th>
                    <th>Active</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {mine.map((rule) => (
                    <tr key={rule.id}>
                      <td className={s.left}>{ALERT_LABELS[rule.kind]}</td>
                      <td className="cn-numeric">
                        {STATE_ONLY.includes(rule.kind) ? '—' : rule.threshold}
                      </td>
                      <td>{rule.lastFiredAt ? fmtIst(new Date(rule.lastFiredAt)) : '—'}</td>
                      <td>
                        <button
                          type="button"
                          className={cx(s.chip, rule.enabled ? s.chipUp : s.chipNeutral)}
                          onClick={() => onToggle(rule.id)}
                          aria-pressed={rule.enabled}
                          style={{ cursor: 'pointer' }}
                        >
                          {rule.enabled ? 'on' : 'off'}
                        </button>
                      </td>
                      <td>
                        <button
                          type="button"
                          className={cx(s.action, s.actionDanger)}
                          onClick={() => onRemove(rule.id)}
                          aria-label="Delete rule"
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

      <section className={s.panel}>
        <div className={s.panelHead}>
          <h2 className={s.panelTitle}>Fired this session</h2>
        </div>
        <div className={s.panelBodyFlush}>
          {fired.length === 0 ? (
            <p className={s.empty}>Nothing has fired since this page loaded.</p>
          ) : (
            <div className={s.tableScroll}>
              <table className={s.table}>
                <thead>
                  <tr>
                    <th className={s.left}>At</th>
                    <th className={s.left}>Symbol</th>
                    <th className={s.left}>What happened</th>
                    <th>Observed</th>
                  </tr>
                </thead>
                <tbody>
                  {fired.map((event, index) => (
                    <tr key={`${event.ruleId}-${event.at}-${index}`}>
                      <td className={s.left}>{fmtIst(new Date(event.at))}</td>
                      <td className={s.left}>{event.symbol}</td>
                      <td className={cx(s.left, s.warn)} style={{ whiteSpace: 'normal' }}>
                        {event.message}
                      </td>
                      <td className="cn-numeric">{event.observed.toFixed(2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </section>

      <section className={s.panel}>
        <div className={s.panelHead}>
          <h2 className={s.panelTitle}>Watchlist</h2>
        </div>
        <div className={s.panelBody}>
          {watchlist.length === 0 ? (
            <p className={s.empty}>
              Nothing saved. Use Watch in the header to keep a symbol here between visits.
            </p>
          ) : (
            <div className={s.toggles}>
              {watchlist.map((entry) => (
                <button
                  key={entry}
                  type="button"
                  className={cx(s.action, entry === symbol && s.actionPrimary)}
                  onClick={() => onPick(entry)}
                >
                  {entry}
                </button>
              ))}
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
