import type { DataSourceName } from '$contexts/broker-connections/types';
import type { ImpliedOpen, Verdict } from '$contexts/global-markets/types';
import DataSourceBadge from '$shared/ui/DataSourceBadge';
import { cx } from '$shared/ui/cx';
import {
  SIGNAL_LABELS,
  fmtChange,
  fmtLevel,
  fmtPercent,
  signalTone,
  tone,
  verdictLine
} from '../gia-data';
import s from './ImpliedOpenCard.module.css';

interface Props {
  implied: ImpliedOpen | null;
  verdict: Verdict;
  source: DataSourceName;
}

/**
 * What GIFT NIFTY is quoting the Indian open at.
 *
 * Deliberately kept apart from the composite next to it. GIFT settles to
 * NIFTY, so it is a direct quote of the very thing being predicted, while the
 * world's indices are inputs to predicting it. Averaging the two into one
 * arrow would erase the most useful state this page has: the nights when they
 * disagree.
 *
 * The verdict below the numbers is where that disagreement is named.
 */
export default function ImpliedOpenCard({ implied, verdict, source }: Props) {
  return (
    <section className={s.wrap} aria-label="GIFT NIFTY implied open">
      <header className={s.head}>
        <div>
          <h2 className={s.title}>GIFT NIFTY — Implied Open</h2>
          <p className={s.sub}>The contract&apos;s own quote of the next Indian open</p>
        </div>
        <DataSourceBadge source={source} />
      </header>

      {implied === null ? (
        <p className={s.empty}>No GIFT NIFTY quote — the implied open cannot be read without it.</p>
      ) : (
        <>
          {/* The contract's own session move leads the card. It is the
              figure that reconciles against a broker screen, and on a quiet
              night it is the only one of the two with anything to say - the
              implied gap sits below with the rest of the working. */}
          <p className={cx(s.gap, 'mc-numeric', s[tone(implied.gift_change) ?? 'flat'])}>
            {fmtChange(implied.gift_change)} ({fmtPercent(implied.gift_change_percent)})
          </p>
          <p className={s.gapLabel}>GIFT day change</p>

          <dl className={s.figures}>
            <div className={s.cell}>
              <dt>GIFT level</dt>
              <dd className="mc-numeric">{fmtLevel(implied.gift_level)}</dd>
            </div>
            {/* Demoted from the headline, not dropped: it is what the card is
                named for, and the verdict line below is read from its sign. */}
            <div className={s.cell}>
              <dt>Implied gap · {SIGNAL_LABELS[implied.signal]}</dt>
              <dd className={cx('mc-numeric', s[signalTone(implied.signal) ?? 'flat'])}>
                {fmtChange(implied.gap_points)} ({fmtPercent(implied.gap_percent)})
              </dd>
            </div>
            <div className={s.cell}>
              <dt>{implied.nifty_is_trading ? 'NIFTY prev close' : 'NIFTY close'}</dt>
              <dd className="mc-numeric">{fmtLevel(implied.reference_close)}</dd>
            </div>
            {/* Once the cash market shuts, spot *is* the reference close and
                the basis *is* the gap. Printing them twice would read as two
                findings where there is one. */}
            {implied.nifty_is_trading ? (
              <>
                <div className={s.cell}>
                  <dt>NIFTY spot</dt>
                  <dd className="mc-numeric">{fmtLevel(implied.nifty_spot)}</dd>
                </div>
                <div className={s.cell}>
                  <dt>Basis to spot</dt>
                  <dd className="mc-numeric">{fmtChange(implied.basis)}</dd>
                </div>
              </>
            ) : null}
          </dl>

          {/* Which close the gap is measured from moves with the clock, so the
              card says which one it used rather than leaving the reader to
              infer it from numbers that only agree half the day. */}
          <p className={s.bases}>
            {implied.nifty_is_trading
              ? 'NIFTY is trading, so the gap is measured from its previous close; the basis is against spot, which has since moved.'
              : 'NIFTY has closed, so the gap is measured from that close — the level the next session opens from. GIFT day change is against GIFT’s own previous settlement, which is why the two differ.'}
          </p>

          <p className={cx(s.verdict, verdict === 'disagree' && s.flagged)}>
            {verdictLine(verdict)}
          </p>
        </>
      )}

      {source === 'mock' ? (
        <p className={s.caveat}>
          NSE IX could not be reached, so this contract is simulated. Everything else on the page is
          live.
        </p>
      ) : null}
    </section>
  );
}
