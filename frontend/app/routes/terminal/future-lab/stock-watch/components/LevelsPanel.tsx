import { useMemo, useState } from 'react';
import { cx } from '$shared/ui/cx';
import type { Candle } from '$shared/charts/tv/LwChart';
import { type LevelKind, type LevelSet, bySession, pivots } from '../calc/levels';
import { EMPTY, fmtIst, fmtPercent, fmtPrice } from '../calc/format';
import s from '../stock-watch.module.css';

/** Groups the reader can switch off, so a crowded panel can be thinned. */
const GROUPS: { id: LevelKind[]; label: string }[] = [
  { id: ['previous_close', 'previous_high', 'previous_low'], label: 'Previous session' },
  { id: ['day_high', 'day_low'], label: "Today's range" },
  { id: ['open_range_high', 'open_range_low'], label: 'Opening range' },
  { id: ['vwap'], label: 'VWAP' },
  { id: ['swing_high', 'swing_low'], label: 'Swings' },
  { id: ['atr_band'], label: 'ATR bands' }
];

interface Props {
  levels: LevelSet;
  candles: Candle[];
  spot?: number | undefined;
  timeframe: string;
}

/**
 * Every level, with where it came from.
 *
 * The source column is the point of this panel. A "previous day high" measured
 * on five-minute bars and one measured on daily bars are the same number only
 * when the intraday series actually reaches back a full session — and a reader
 * who takes a level off here and marks it on a different timeframe needs to
 * know which one produced it.
 *
 * Distance to spot is shown because that is what decides whether a level
 * matters today: a swing high 9% away is history, not a target.
 */
export default function LevelsPanel({ levels, candles, spot, timeframe }: Props) {
  const [hidden, setHidden] = useState<Set<string>>(() => new Set());
  const [showPivots, setShowPivots] = useState(false);

  const visible = useMemo(() => {
    const off = new Set<LevelKind>();
    for (const group of GROUPS) {
      if (hidden.has(group.label)) for (const kind of group.id) off.add(kind);
    }
    return levels.levels.filter((level) => !off.has(level.kind)).sort((a, b) => b.price - a.price);
  }, [levels, hidden]);

  const floor = useMemo(() => {
    const sessions = bySession(candles);
    const previous = sessions.length >= 2 ? sessions[sessions.length - 2] : undefined;
    if (!previous || previous.bars.length === 0) return undefined;
    const high = Math.max(...previous.bars.map((bar) => bar.high));
    const low = Math.min(...previous.bars.map((bar) => bar.low));
    const close = previous.bars[previous.bars.length - 1]?.close;
    if (close == null) return undefined;
    return { day: previous.day, ...pivots({ high, low, close }) };
  }, [candles]);

  const toggle = (label: string) =>
    setHidden((previous) => {
      const next = new Set(previous);
      if (next.has(label)) next.delete(label);
      else next.add(label);
      return next;
    });

  return (
    <section className={s.panel}>
      <div className={s.panelHead}>
        <div>
          <h2 className={s.panelTitle}>Technical levels</h2>
          <p className={s.panelSub}>
            All measured on {timeframe} bars
            {levels.sessionDay ? ` · session ${levels.sessionDay}` : ''}
          </p>
        </div>
        <div className={s.panelActions}>
          {GROUPS.map((group) => (
            <button
              key={group.label}
              type="button"
              className={cx(s.action, !hidden.has(group.label) && s.actionPrimary)}
              aria-pressed={!hidden.has(group.label)}
              onClick={() => toggle(group.label)}
            >
              {group.label}
            </button>
          ))}
          <button
            type="button"
            className={cx(s.action, showPivots && s.actionPrimary)}
            aria-pressed={showPivots}
            onClick={() => setShowPivots((on) => !on)}
          >
            Pivots
          </button>
        </div>
      </div>

      <div className={s.panelBodyFlush}>
        {levels.previousSessionMissing ? (
          <p className={cx(s.notice, s.noticeWarn)} style={{ margin: 'var(--cn-space-3)' }}>
            <span>
              This series does not reach back a full prior session, so previous-day levels and the
              gap read are unavailable at this interval. Switch to a longer bar size or a wider
              range.
            </span>
          </p>
        ) : null}

        {visible.length === 0 ? (
          <p className={s.empty}>Every group is switched off.</p>
        ) : (
          <div className={s.tableScroll}>
            <table className={s.table}>
              <thead>
                <tr>
                  <th className={s.left}>Level</th>
                  <th>Price</th>
                  <th>Distance</th>
                  <th>Timeframe</th>
                  <th>Measured</th>
                  <th className={s.left}>How it was calculated</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((level) => {
                  const distance =
                    spot != null && spot > 0 ? ((level.price - spot) / spot) * 100 : undefined;
                  return (
                    <tr key={`${level.kind}-${level.label}`}>
                      <td className={s.left}>{level.label}</td>
                      <td className="cn-numeric">{fmtPrice(level.price)}</td>
                      <td
                        className={cx(
                          'cn-numeric',
                          distance != null ? (distance > 0 ? s.up : s.down) : undefined
                        )}
                      >
                        {fmtPercent(distance)}
                      </td>
                      <td>{level.timeframe}</td>
                      <td>{level.asOf ? fmtIst(level.asOf) : EMPTY}</td>
                      <td className={cx(s.left, s.muted)} style={{ whiteSpace: 'normal' }}>
                        {level.method}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {showPivots ? (
          floor ? (
            <div className={s.panelBody}>
              <p className={s.panelSub} style={{ marginBottom: 'var(--cn-space-2)' }}>
                Classic floor pivots from the {floor.day} session&apos;s high, low and close.
              </p>
              <dl className={s.readout} style={{ borderTop: 0, paddingTop: 0 }}>
                {(
                  [
                    ['R3', floor.r3],
                    ['R2', floor.r2],
                    ['R1', floor.r1],
                    ['Pivot', floor.pivot],
                    ['S1', floor.s1],
                    ['S2', floor.s2],
                    ['S3', floor.s3]
                  ] as const
                ).map(([label, value]) => (
                  <div key={label}>
                    <dt className={s.readoutKey}>{label}</dt>
                    <dd className={cx(s.readoutValue, 'cn-numeric')}>{fmtPrice(value)}</dd>
                  </div>
                ))}
              </dl>
            </div>
          ) : (
            <p className={s.empty}>Pivots need a complete previous session on this timeframe.</p>
          )
        ) : null}

        <p className={s.notice} style={{ margin: 'var(--cn-space-3)' }}>
          <span>
            These are prices where buyers or sellers previously won, computed by the stated rule and
            nothing more. Nothing here identifies institutional activity or a liquidity pool — the
            candle data cannot support that claim, and a level is only as good as what price does
            when it gets there.
          </span>
        </p>
      </div>
    </section>
  );
}
