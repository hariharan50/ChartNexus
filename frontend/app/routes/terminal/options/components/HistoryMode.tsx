import { cx } from '$shared/ui/cx';
import DatePicker from '$shared/ui/DatePicker';
import { isoDateIST } from '$shared/formatting/ist-clock';
import s from './HistoryMode.module.css';

export type Mode = 'live' | 'historical';

/**
 * The Live / Historical switch shared by every OI tool.
 *
 * Live reads today's session; Historical replays an archived past day, picked
 * from the date input that appears only in that mode. The archive reaches back
 * `snapshot_retention_days`, and a day nothing was captured simply renders empty
 * — the page's own no-data state handles it, so this control stays presentational.
 */
interface Props {
  mode: Mode;
  date: string;
  onMode: (mode: Mode) => void;
  onDate: (date: string) => void;
}

export default function HistoryMode({ mode, date, onMode, onDate }: Props) {
  return (
    <>
      <p className={s.label}>Select Mode</p>
      <div className={s.grid} role="tablist" aria-label="Data mode">
        <button
          type="button"
          role="tab"
          aria-selected={mode === 'live'}
          className={cx(s.seg, mode === 'live' && s.active)}
          onClick={() => onMode('live')}
        >
          Live
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={mode === 'historical'}
          className={cx(s.seg, mode === 'historical' && s.active)}
          onClick={() => onMode('historical')}
        >
          Historical
        </button>
      </div>

      {mode === 'historical' ? (
        <>
          <p className={s.label}>Session date</p>
          <DatePicker value={date} max={isoDateIST(0)} onChange={onDate} ariaLabel="Session date" />
        </>
      ) : null}
    </>
  );
}
