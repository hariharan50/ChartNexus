import { useEffect, useState } from 'react';
import {
  type GapForecast,
  countdownLabel,
  inPreOpenWatch,
  minutesToOpen
} from '$contexts/market-data/gap-forecast';
import type { GapReading, GapSignal } from '$contexts/market-data/view-models';
import { cx } from '$shared/ui/cx';
import IconStep from '$shared/ui/icons/IconStep';
import s from './GapIndicatorCard.module.css';
import Panel from './Panel';

interface Props {
  /** The session's opening print. Absent until the bell has actually rung. */
  reading?: GapReading | undefined;
  /** The pre-open estimate, shown only while there is no print to replace it. */
  forecast?: GapForecast | undefined;
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

const CONFIDENCE: Record<GapForecast['confidence'], string> = {
  high: 'High confidence',
  medium: 'Medium confidence',
  low: 'Low confidence'
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
 * Minutes to the bell, re-read every thirty seconds.
 *
 * Off the exchange clock rather than the server's timestamp, for the reason
 * `ist-clock` gives: a countdown that freezes the moment a request fails is
 * worse than one the browser can always answer. The figures beside it are
 * server-derived; only this line is local.
 */
function useMinutesToOpen(active: boolean): number {
  const [minutes, setMinutes] = useState(() => minutesToOpen());

  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(() => setMinutes(minutesToOpen()), 30_000);
    return () => window.clearInterval(timer);
  }, [active]);

  return minutes;
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
      text: 'Provisional — the opening auction has only just run, so this print can still be corrected.'
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
 * It renders what the backend decided and nothing it worked out itself. That
 * is a deliberate reversal: the card used to recompute the gap from every
 * fifteen-second spot poll, and a poll that degraded to the mock provider
 * carried a different open *and* a different previous close, so the verdict
 * flipped from GAP UP to GAP DOWN and back with the broker's circuit breaker.
 *
 * **Two readings, never blended.** Before the bell there is no opening print —
 * the backend says so by sending no gap at all — and the card shows the GIFT
 * NIFTY forecast instead, under an EXPECTED tag with a countdown to the open.
 * Once the auction prints, the measurement replaces the estimate and the card
 * stops predicting. Which of the two is on screen is stated, never implied:
 * an estimate a reader mistakes for a print is worse than no card.
 */
export default function GapIndicatorCard({ reading, forecast, loading = false, label }: Props) {
  const showForecast = !reading && !!forecast;
  // Nothing to say yet and the bell is still ahead: the card counts down
  // rather than claiming a gap it cannot have.
  const waiting = !reading && !forecast && inPreOpenWatch();
  const minutes = useMinutesToOpen(showForecast || waiting);
  const note = reading ? provenanceNote(reading) : undefined;

  return (
    <Panel
      title={`${reading?.label ?? forecast?.label ?? label} Gap`}
      subtitle={showForecast ? 'Expected open · pre-market' : undefined}
      icon={<IconStep />}
    >
      {loading && !forecast ? (
        <div className={s.skeleton} aria-hidden="true">
          <span className={s.skelPill} />
          <span className={s.skelRow} />
        </div>
      ) : reading ? (
        <div className={s.body}>
          <div className={s.verdictRow}>
            <p className={cx(s.verdict, s[reading.signal])}>{VERDICT[reading.signal]}</p>
            <p className={cx(s.gap, s[reading.signal], 'cn-numeric')}>
              {signed(reading.points, 2)} ({signed(reading.percent, 2)}%)
            </p>
          </div>

          <div className={s.figures}>
            <div className={s.cell}>
              <p className={s.key}>Open</p>
              <p className={cx(s.figure, 'cn-numeric')}>{level(reading.open)}</p>
            </div>
            <div className={s.cell}>
              <p className={s.key}>Prev Close</p>
              <p className={cx(s.figure, 'cn-numeric')}>{level(reading.previousClose)}</p>
            </div>
          </div>

          {/* Grouped with the figures rather than left to the body's own
              spacing: the note qualifies this reading, and a full row's gap
              would read as a separate section. */}
          {note ? (
            <p className={cx(s.note, note.tone === 'warn' && s.noteWarn)}>{note.text}</p>
          ) : null}
        </div>
      ) : forecast ? (
        <div className={s.body}>
          <div className={s.verdictRow}>
            {/* EXPECTED rides inside the pill rather than beside it. The
                verdict and its tense are one statement, and a reader
                glancing at the rail must not be able to take the colour
                without the qualifier. */}
            <p className={cx(s.verdict, s[forecast.signal])}>
              <span className={s.expected}>Expected</span>
              {VERDICT[forecast.signal]}
            </p>
            <p className={cx(s.gap, s[forecast.signal], 'cn-numeric')}>
              {signed(forecast.points, 2)} ({signed(forecast.percent, 2)}%)
            </p>
          </div>

          <div className={s.figures}>
            <div className={s.cell}>
              <p className={s.key}>GIFT NIFTY</p>
              <p className={cx(s.figure, 'cn-numeric')}>{level(forecast.impliedLevel)}</p>
            </div>
            <div className={s.cell}>
              <p className={s.key}>Prev Close</p>
              <p className={cx(s.figure, 'cn-numeric')}>{level(forecast.referenceClose)}</p>
            </div>
          </div>

          <div className={s.statusRow}>
            <span className={s.countdown}>Opens 09:15 IST · in {countdownLabel(minutes)}</span>
            <span className={cx(s.confidence, s[`conf_${forecast.confidence}`])}>
              {CONFIDENCE[forecast.confidence]}
            </span>
          </div>

          <p className={cx(s.note, forecast.source === 'mock' && s.noteWarn)}>
            {forecast.confidenceReason}
          </p>
          <p className={s.note}>
            Forecast from GIFT NIFTY, which settles to NIFTY and trades overnight — read at{' '}
            {clockTime(forecast.asOf)} IST and free to move until the bell. The gap is confirmed
            against the real opening print at 09:15.
          </p>
        </div>
      ) : waiting ? (
        <div className={s.body}>
          <p className={s.countdown}>Opens 09:15 IST · in {countdownLabel(minutes)}</p>
          <p className={s.unavailable}>
            No opening print yet, and no overnight contract quoting {label}&apos;s open — the gap is
            measured at the bell.
          </p>
        </div>
      ) : (
        <p className={s.unavailable}>Gap unavailable — no opening print yet.</p>
      )}
    </Panel>
  );
}
