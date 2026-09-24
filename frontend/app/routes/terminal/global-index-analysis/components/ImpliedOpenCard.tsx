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
          <p className={s.sub}>The contract&apos;s own quote of tomorrow&apos;s open</p>
        </div>
        <DataSourceBadge source={source} />
      </header>

      {implied === null ? (
        <p className={s.empty}>No GIFT NIFTY quote — the implied open cannot be read without it.</p>
      ) : (
        <>
          <p className={cx(s.signal, s[signalTone(implied.signal) ?? 'flat'])}>
            {SIGNAL_LABELS[implied.signal]}
          </p>

          <p className={cx(s.gap, 'mc-numeric', s[signalTone(implied.signal) ?? 'flat'])}>
            {fmtChange(implied.gap_points)} ({fmtPercent(implied.gap_percent)})
          </p>

          <dl className={s.figures}>
            <div className={s.cell}>
              <dt>GIFT level</dt>
              <dd className="mc-numeric">{fmtLevel(implied.gift_level)}</dd>
            </div>
            <div className={s.cell}>
              <dt>NIFTY prev close</dt>
              <dd className="mc-numeric">{fmtLevel(implied.nifty_previous_close)}</dd>
            </div>
            <div className={s.cell}>
              <dt>NIFTY spot</dt>
              <dd className="mc-numeric">{fmtLevel(implied.nifty_spot)}</dd>
            </div>
            <div className={s.cell}>
              <dt>Basis to spot</dt>
              <dd className="mc-numeric">{fmtChange(implied.basis)}</dd>
            </div>
          </dl>

          {/* Two discounts of different sizes on one card reads as a
              contradiction unless both bases are named. */}
          <p className={s.bases}>
            The gap is measured from the previous close; the basis is against spot, which has since
            moved.
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
