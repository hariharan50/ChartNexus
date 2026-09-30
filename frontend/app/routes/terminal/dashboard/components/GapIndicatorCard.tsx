import type { GapReading, GapSignal } from '$contexts/market-data/view-models';
import { cx } from '$shared/ui/cx';
import IconStep from '$shared/ui/icons/IconStep';
import s from './GapIndicatorCard.module.css';
import Panel from './Panel';

interface Props {
  /** Absent until the session has a believable opening pair. */
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

/** 09:16:04 — the reading is a moment, not a date; the card is only ever
    showing today's (or, over a weekend, the last session's). */
function clockTime(at: Date): string {
  return at.toLocaleTimeString('en-IN', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone: 'Asia/Kolkata'
  });
}

/**
 * What the card has to say about the pair it is showing, beyond the numbers.
 *
 * There are three different things a reader needs to be told apart, and the old
 * card told them none: this is the real opening print (say when it was taken);
 * this is simulated (say so outright); this is the broker's pre-open
 * placeholder and will be replaced once the auction runs.
 */
function provenanceNote(reading: GapReading): { tone: 'plain' | 'warn'; text: string } {
  if (!reading.settled) {
    return {
      tone: 'warn',
      text: 'Provisional — the opening auction has not printed yet, so this is the broker’s pre-open placeholder.'
    };
  }
  if (reading.source === 'mock') {
    return {
      tone: 'warn',
      text: 'Simulated — no live broker feed, so this gap is synthetic and not safe to trade on.'
    };
  }
  // Still worth saying, as the old static caveat did: this is the broker's
  // first reported print, not the exchange's pre-open auction price. The two
  // are usually within a few points and occasionally are not.
  const taken = clockTime(reading.observedAt);
  if (reading.source === 'cached') {
    return { tone: 'plain', text: `Last live reading, taken at ${taken} IST.` };
  }
  return {
    tone: 'plain',
    text: `Broker's first print at ${taken} IST — an approximate open, fixed for the session.`
  };
}

/**
 * The dashboard rail's overnight-gap card.
 *
 * It renders the reading the backend latched and nothing it worked out itself.
 * That is a deliberate reversal: the card used to recompute the gap from every
 * fifteen-second spot poll, and a poll that degraded to the mock provider
 * carried a different open *and* a different previous close, so the verdict
 * flipped from GAP UP to GAP DOWN and back with the broker's circuit breaker.
 *
 * The consequence for the layout is that the card now has something to say
 * about *which* reading it is showing — live, cached, simulated, or a pre-open
 * placeholder — so the note under the figures carries that instead of the
 * static caveat it used to repeat.
 */
export default function GapIndicatorCard({ reading, loading = false, label }: Props) {
  const note = reading ? provenanceNote(reading) : undefined;

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
          <div className={s.verdictRow}>
            <p className={cx(s.verdict, s[reading.signal])}>{VERDICT[reading.signal]}</p>
            <p className={cx(s.gap, s[reading.signal], 'mc-numeric')}>
              {signed(reading.points, 2)} ({signed(reading.percent, 2)}%)
            </p>
          </div>

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

          {/* Grouped with the figures rather than left to the body's own
              spacing: the note qualifies this reading, and a full row's gap
              would read as a separate section. */}
          {note ? (
            <p className={cx(s.note, note.tone === 'warn' && s.noteWarn)}>{note.text}</p>
          ) : null}
        </div>
      )}
    </Panel>
  );
}
