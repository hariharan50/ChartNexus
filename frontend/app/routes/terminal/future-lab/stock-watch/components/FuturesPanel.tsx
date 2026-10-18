import type { FuturesQuote } from '$contexts/broker-connections/types';
import type { FuturesRow } from '$contexts/futures-analytics/types';
import { cx } from '$shared/ui/cx';
import { type Basis, rolloverPercent } from '../calc/analytics';
import {
  EMPTY,
  fmtDate,
  fmtIndian,
  fmtPercent,
  fmtPrice,
  fmtSigned,
  tone,
  wire
} from '../calc/format';
import s from '../stock-watch.module.css';

/** The 2×2, as the futures board classifies it. */
const STATE_LABEL: Record<string, string> = {
  long_buildup: 'Long buildup',
  short_buildup: 'Short buildup',
  short_covering: 'Short covering',
  long_unwinding: 'Long unwinding',
  neutral: 'No clear pattern'
};

const STATE_TONE: Record<string, 'up' | 'down' | null> = {
  long_buildup: 'up',
  short_covering: 'up',
  short_buildup: 'down',
  long_unwinding: 'down',
  neutral: null
};

/** What each quadrant actually means, for the tooltip and the explainer row. */
const STATE_RULE: Record<string, string> = {
  long_buildup: 'Price up with open interest up — money entering on the long side.',
  short_buildup: 'Price down with open interest up — money entering on the short side.',
  short_covering: 'Price up with open interest down — shorts closing out.',
  long_unwinding: 'Price down with open interest down — longs closing out.',
  neutral: 'Neither price nor open interest moved enough to call a direction.'
};

interface Props {
  symbol: string;
  futures?: FuturesQuote | undefined;
  spot?: number | undefined;
  basis?: Basis | undefined;
  nearRow?: FuturesRow | undefined;
  nextRow?: FuturesRow | undefined;
  /** False when no open-interest sweep covered this series — see the board. */
  hasOpenInterest: boolean;
  loading: boolean;
}

/**
 * What the futures contract is doing, and what the price/OI pair implies.
 *
 * The classification is a heuristic and the panel says so in place, not in a
 * footnote. Rising open interest means money entered the contract; it does not
 * say who entered it or why, and a hedge against a cash position builds open
 * interest exactly like a directional bet does. The underlying's own move and
 * the OI change are printed beside the verdict so the reader can check the
 * inference rather than take it.
 */
export default function FuturesPanel({
  symbol,
  futures,
  spot,
  basis,
  nearRow,
  nextRow,
  hasOpenInterest,
  loading
}: Props) {
  const price = wire(futures?.price);
  const changePercent = wire(futures?.change_percent);
  const nearOi = nearRow?.open_interest ?? undefined;
  const nextOi = nextRow?.open_interest ?? undefined;
  const rollover = rolloverPercent(nearOi ?? undefined, nextOi ?? undefined);
  const state = nearRow?.state ?? 'neutral';
  const stateTone = STATE_TONE[state] ?? null;
  const oiChangePercent = wire(nearRow?.oi_change_percent);

  return (
    <section className={s.panel}>
      <div className={s.panelHead}>
        <div>
          <h2 className={s.panelTitle}>Futures positioning</h2>
          <p className={s.panelSub}>
            {futures?.contract ?? symbol}
            {futures?.expiry ? ` · expires ${fmtDate(futures.expiry)}` : ''}
          </p>
        </div>
        {hasOpenInterest ? (
          <span
            className={cx(
              s.chip,
              stateTone ? s[`chip${stateTone === 'up' ? 'Up' : 'Down'}`] : s.chipNeutral
            )}
          >
            {STATE_LABEL[state] ?? state}
          </span>
        ) : (
          <span className={cx(s.chip, s.chipWarn)}>OI not measured</span>
        )}
      </div>

      <div className={s.panelBody}>
        {loading && !futures ? (
          <div className={s.skeleton} aria-hidden="true">
            <span className={s.skeletonRow} />
            <span className={s.skeletonRow} />
          </div>
        ) : (
          <>
            <dl className={s.rows}>
              <div className={s.rowLine}>
                <dt>Near month</dt>
                <dd className={cx(tone(changePercent) ? s[tone(changePercent)!] : undefined)}>
                  {fmtPrice(price)} ({fmtPercent(changePercent)})
                </dd>
              </div>
              <div className={s.rowLine}>
                <dt>Next month</dt>
                <dd>
                  {nextRow ? fmtPrice(wire(nextRow.price)) : EMPTY}
                  {nextRow && price != null && wire(nextRow.price) != null ? (
                    <span className={s.muted}>
                      {' '}
                      ({fmtSigned((wire(nextRow.price) ?? 0) - price)} vs near)
                    </span>
                  ) : null}
                </dd>
              </div>
              <div className={s.rowLine}>
                <dt>Volume</dt>
                <dd>{fmtIndian(futures?.volume ?? nearRow?.volume ?? undefined)}</dd>
              </div>
              <div className={s.rowLine}>
                <dt>Open interest</dt>
                <dd>{nearOi != null ? fmtIndian(nearOi) : EMPTY}</dd>
              </div>
              <div className={s.rowLine}>
                <dt>OI change</dt>
                <dd className={cx(tone(oiChangePercent) ? s[tone(oiChangePercent)!] : undefined)}>
                  {fmtPercent(oiChangePercent)}
                </dd>
              </div>
              <div className={s.rowLine}>
                <dt>Basis to spot</dt>
                <dd
                  className={cx(basis && tone(basis.points) ? s[tone(basis.points)!] : undefined)}
                >
                  {basis ? `${fmtSigned(basis.points)} (${fmtPercent(basis.percent)})` : EMPTY}
                </dd>
              </div>
              <div className={s.rowLine}>
                <dt>Spot</dt>
                <dd>{fmtPrice(spot)}</dd>
              </div>
              <div className={s.rowLine}>
                <dt>Rollover to next</dt>
                <dd>{rollover != null ? `${rollover.toFixed(1)}%` : EMPTY}</dd>
              </div>
              <div className={s.rowLine}>
                <dt>Day marker</dt>
                <dd>{nearRow?.open_marker ?? EMPTY}</dd>
              </div>
            </dl>

            {/* The working, next to the verdict. A reader who disagrees with
                the classification can see exactly which two numbers produced
                it, which is the difference between a tool and an oracle. */}
            <p className={s.notice} style={{ marginTop: 'var(--cn-space-3)' }}>
              <span>
                <strong>{STATE_LABEL[state] ?? state}.</strong> {STATE_RULE[state]} This is a
                heuristic about the <em>contract</em>, not proof of intent: a hedge against a cash
                position builds open interest exactly as a directional bet does, and open interest
                never says who is on which side.
              </span>
            </p>

            {rollover == null ? (
              <p className={cx(s.notice, s.noticeWarn)} style={{ marginTop: 'var(--cn-space-2)' }}>
                <span>
                  Rollover needs open interest on both the near and the next month. One of the two
                  was not priced, so the figure is withheld rather than reported as 0%.
                </span>
              </p>
            ) : null}
          </>
        )}
      </div>
    </section>
  );
}
