import { BREADTH_INTERVALS, type BreadthInterval } from '$contexts/market-breadth/api';
import DatePicker from '$shared/ui/DatePicker';
import { cx } from '$shared/ui/cx';
import s from './BreadthControls.module.css';

export type BreadthMode = 'live' | 'historical';

interface Props {
  interval: BreadthInterval;
  onInterval: (interval: BreadthInterval) => void;
  mode: BreadthMode;
  onMode: (mode: BreadthMode) => void;
  /** ISO date; only read in historical mode. */
  date: string;
  onDate: (date: string) => void;
  /** Sessions the archive actually holds, newest first. */
  sessions: string[];
  weighted: boolean;
  onWeighted: (weighted: boolean) => void;
  /**
   * False when the scope carries no index weights — every sector. The control
   * stays visible and disabled with a reason rather than vanishing: a toggle
   * that appears and disappears as you move down the rail reads as a bug.
   */
  weightedAvailable: boolean;
}

/**
 * What the two cards to the right are scoped to.
 *
 * One row of controls above everything they govern, never inside a chart card.
 * Historical offers only sessions the archive holds — the capture worker keeps
 * thirty days, and a date picker offering a day nobody captured is a promise
 * the page cannot keep.
 */
export default function BreadthControls({
  interval,
  onInterval,
  mode,
  onMode,
  date,
  onDate,
  sessions,
  weighted,
  onWeighted,
  weightedAvailable
}: Props) {
  const earliest = sessions.length > 0 ? sessions[sessions.length - 1]! : undefined;
  const latest = sessions.length > 0 ? sessions[0]! : undefined;

  return (
    <div className={s.controls}>
      <div className={s.group} role="group" aria-label="Bucket width">
        <span className={s.caption}>Interval</span>
        <div className={s.segmented}>
          {BREADTH_INTERVALS.map((entry) => (
            <button
              key={entry}
              type="button"
              className={cx(s.seg, entry === interval && s.segOn)}
              aria-pressed={entry === interval}
              onClick={() => onInterval(entry)}
            >
              {entry}
            </button>
          ))}
        </div>
      </div>

      <div className={s.group} role="group" aria-label="Data mode">
        <span className={s.caption}>Mode</span>
        <div className={s.segmented}>
          {(['live', 'historical'] as BreadthMode[]).map((entry) => (
            <button
              key={entry}
              type="button"
              className={cx(s.seg, entry === mode && s.segOn)}
              aria-pressed={entry === mode}
              disabled={entry === 'historical' && sessions.length === 0}
              title={
                entry === 'historical' && sessions.length === 0
                  ? 'No session has been captured yet'
                  : undefined
              }
              onClick={() => onMode(entry)}
            >
              {entry === 'live' ? 'Live' : 'Historical'}
            </button>
          ))}
        </div>
      </div>

      {mode === 'historical' ? (
        <div className={s.group}>
          <span className={s.caption}>Session</span>
          <DatePicker
            value={date}
            {...(earliest ? { min: earliest } : {})}
            {...(latest ? { max: latest } : {})}
            onChange={onDate}
            ariaLabel="Archived session"
          />
        </div>
      ) : null}

      <label
        className={cx(s.group, s.toggle, !weightedAvailable && s.disabled)}
        title={
          weightedAvailable
            ? 'Plot the index weight behind each side instead of the head count'
            : 'These names carry no index weight — only a tracked index has one'
        }
      >
        <input
          type="checkbox"
          checked={weighted && weightedAvailable}
          disabled={!weightedAvailable}
          onChange={(event) => onWeighted(event.currentTarget.checked)}
        />
        <span className={s.caption}>Weighted</span>
        <span className={s.sub}>by index weight</span>
      </label>
    </div>
  );
}
