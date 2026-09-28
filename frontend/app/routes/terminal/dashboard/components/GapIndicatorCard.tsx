import type { GapReading, GapSignal } from '$contexts/market-data/view-models';
import { cx } from '$shared/ui/cx';
import IconStep from '$shared/ui/icons/IconStep';
import s from './GapIndicatorCard.module.css';
import Panel from './Panel';

interface Props {
  /** Absent when the broker did not supply an open and a previous close. */
  reading?: GapReading | undefined;
  /** The spot query is still in flight. */
  loading?: boolean;
  /** Panel title falls back to this while there is nothing to read. */
  label: string;
}

const VERDICT: Record<GapSignal, string> = {
  gap_up: 'GAP UP',
  gap_down: 'GAP DOWN',
  flat: 'FLAT'
};

/** Index levels carry two decimals everywhere else on this page. */
function level(value: number): string {
  return value.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

/** Signed, with a true minus sign — the gap's direction is the whole point. */
function signed(value: number, digits: number): string {
  const sign = value > 0 ? '+' : value < 0 ? '−' : '';
  return `${sign}${Math.abs(value).toFixed(digits)}`;
}

export default function GapIndicatorCard({ reading, loading = false, label }: Props) {
  return (
    <Panel title={`${reading?.label ?? label} Gap`} icon={<IconStep />}>
      {loading ? (
        <div className={s.skeleton} aria-hidden="true">
          <span className={s.skelPill} />
          <span className={s.skelRow} />
        </div>
      ) : !reading ? (
        <p className={s.unavailable}>Gap unavailable — no opening print yet.</p>
      ) : (
        <div className={s.body}>
          <p className={cx(s.verdict, s[reading.signal])}>{VERDICT[reading.signal]}</p>

          <div className={s.figures}>
            <div className={s.cell}>
              <p className={s.key}>Open</p>
              <p className={cx(s.figure, 'mc-numeric')}>{level(reading.open)}</p>
            </div>
            <div className={s.cell}>
              <p className={s.key}>Prev Close</p>
              <p className={cx(s.figure, 'mc-numeric')}>{level(reading.previousClose)}</p>
            </div>
          </div>

          {/* The caveat belongs to the gap, so it is grouped with it rather
              than left to the body's own spacing - a rule or a full row's gap
              would read as a separate section and change the card's shape.

              Why it is there: the open is the broker's first reported print,
              not the exchange's pre-open auction price. The two are usually
              within a few points and occasionally are not, and a gap quoted to
              two decimals invites more precision than the input carries. */}
          <div className={s.gapBlock}>
            <p className={cx(s.gap, s[reading.signal], 'mc-numeric')}>
              {signed(reading.points, 2)} ({signed(reading.percent, 2)}%)
            </p>
            <p className={s.note}>
              Open is the broker&apos;s first reported print — an approximate opening level, not the
              exchange&apos;s official open.
            </p>
          </div>
        </div>
      )}
    </Panel>
  );
}
