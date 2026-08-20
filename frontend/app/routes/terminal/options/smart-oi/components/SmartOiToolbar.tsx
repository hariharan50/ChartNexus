import { cx } from '$shared/ui/cx';
import DatePicker from '$shared/ui/DatePicker';
import IconChevronDown from '$shared/ui/icons/IconChevronDown';
import { isoDateIST } from '$shared/formatting/ist-clock';
import type { Mode } from '../../components/HistoryMode';
import {
  INTERVALS,
  SPANS,
  STALE_AFTER_MS,
  clockLabel,
  dateLabel,
  expiryLabel,
  freshnessLabel,
  windowLabel,
  type Instrument,
  type Interval,
  type RangeMode,
  type StrikeMode
} from '../smart-oi-data';
import s from './SmartOiToolbar.module.css';

/**
 * The page header: two rows of controls above the charts.
 *
 * A horizontal toolbar rather than the left sidebar the other Options Lab tools
 * use. That is a deliberate departure: this page is two chart columns wide with
 * nothing to spare, and the controls it carries — interval, expiry, strike
 * window — are ones the reader changes constantly and wants on the same line as
 * the instrument they apply to.
 *
 * Row one is *what* is being looked at, row two is *how much of it*.
 */
interface Props {
  instrument: Instrument;
  onCycle: (step: number) => void;

  expiry: string | undefined;
  expiries: string[];
  /** What the backend actually resolved to, echoed when nothing is picked. */
  resolvedExpiry: string | null;
  onExpiry: (expiry: string | undefined) => void;

  interval: Interval;
  onInterval: (interval: Interval) => void;

  dataMode: Mode;
  date: string;
  onDataMode: (mode: Mode) => void;
  onDate: (date: string) => void;

  replay: boolean;
  onReplay: (on: boolean) => void;

  rangeMode: RangeMode;
  onRangeMode: (mode: RangeMode) => void;
  strikeMode: StrikeMode;
  onStrikeMode: (mode: StrikeMode) => void;
  span: number | null;
  onSpan: (span: number | null) => void;
  custom: { low: string; high: string };
  onCustom: (custom: { low: string; high: string }) => void;

  strikeLow: number | null;
  strikeHigh: number | null;

  now: number;
  updatedAt: number;
  period: number;
  fetching: boolean;
}

export default function SmartOiToolbar(props: Props) {
  const paused = props.dataMode !== 'live' || props.replay;
  const isStale =
    !paused && Boolean(props.updatedAt) && props.now - props.updatedAt > STALE_AFTER_MS;

  return (
    <div className={s.toolbar}>
      <div className={s.row}>
        <div className={s.instrument}>
          <span className={s.badge}>{props.instrument.badge}</span>
          <span className={s.short}>{props.instrument.short}</span>
          <span className={s.cyclers}>
            <button
              type="button"
              aria-label="Previous instrument"
              onClick={() => props.onCycle(-1)}
            >
              ‹
            </button>
            <button type="button" aria-label="Next instrument" onClick={() => props.onCycle(1)}>
              ›
            </button>
          </span>
        </div>

        <div className={s.expiry}>
          <select
            className={s.expirySelect}
            aria-label="Expiry"
            value={props.expiry ?? ''}
            onChange={(e) => props.onExpiry(e.currentTarget.value || undefined)}
          >
            {/* The empty option is "whatever the backend picks", which is the
                nearest expiry and the only one the snapshot archive holds. */}
            <option value="">{expiryLabel(props.resolvedExpiry)}</option>
            {props.expiries.map((iso) => (
              <option key={iso} value={iso}>
                {expiryLabel(iso)}
              </option>
            ))}
          </select>
          <span className={s.caret} aria-hidden="true">
            <IconChevronDown />
          </span>
        </div>

        <div className={s.seg} role="group" aria-label="Interval">
          {INTERVALS.map((entry) => (
            <button
              key={entry.value}
              type="button"
              className={cx(s.segBtn, props.interval === entry.value && s.active)}
              aria-pressed={props.interval === entry.value}
              onClick={() => props.onInterval(entry.value)}
            >
              {entry.label}
            </button>
          ))}
        </div>

        <div className={s.seg} role="tablist" aria-label="Data mode">
          <button
            type="button"
            role="tab"
            aria-selected={props.dataMode === 'live'}
            className={cx(s.segBtn, props.dataMode === 'live' && s.active)}
            onClick={() => props.onDataMode('live')}
          >
            Live
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={props.dataMode === 'historical'}
            className={cx(s.segBtn, props.dataMode === 'historical' && s.active)}
            onClick={() => props.onDataMode('historical')}
          >
            Historical
          </button>
        </div>

        {props.dataMode === 'historical' ? (
          <div className={s.datePick}>
            <DatePicker
              value={props.date}
              max={isoDateIST(0)}
              onChange={props.onDate}
              ariaLabel="Session date"
            />
          </div>
        ) : null}

        <div className={s.rowEnd}>
          <label className={s.switch}>
            <span>Replay</span>
            <input
              type="checkbox"
              checked={props.replay}
              onChange={(e) => props.onReplay(e.currentTarget.checked)}
            />
            <span className={s.track} aria-hidden="true">
              <span className={s.knob} />
            </span>
          </label>

          {paused ? (
            <span className={s.clock}>
              {props.dataMode === 'historical' ? <>Archived · {props.date}</> : 'Replay'}
            </span>
          ) : (
            <span className={cx(s.live, isStale && s.stale)}>
              <span className={cx(s.dot, props.fetching && s.pulse)} />
              <span>
                {dateLabel(props.now)}, {clockLabel(props.now)} IST
              </span>
              <span className={s.sep} aria-hidden="true">
                ·
              </span>
              <span>{props.period / 1000}s</span>
              <span className={s.sep} aria-hidden="true">
                ·
              </span>
              <span>updated {freshnessLabel(props.updatedAt, props.now)}</span>
            </span>
          )}
        </div>
      </div>

      <div className={cx(s.row, s.rowTwo)}>
        <div className={s.seg} role="tablist" aria-label="Strike range source">
          <button
            type="button"
            role="tab"
            aria-selected={props.rangeMode === 'range'}
            className={cx(s.segBtn, props.rangeMode === 'range' && s.active)}
            onClick={() => props.onRangeMode('range')}
          >
            Range
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={props.rangeMode === 'custom'}
            className={cx(s.segBtn, props.rangeMode === 'custom' && s.active)}
            onClick={() => props.onRangeMode('custom')}
          >
            Custom
          </button>
        </div>

        {props.rangeMode === 'range' ? (
          <>
            <span className={s.label}>Mode:</span>
            <div className={s.seg} role="group" aria-label="Strike window mode">
              <button
                type="button"
                className={cx(s.segBtn, props.strikeMode === 'auto' && s.active)}
                aria-pressed={props.strikeMode === 'auto'}
                onClick={() => props.onStrikeMode('auto')}
                title="Re-centre the window on every capture's ATM"
              >
                Auto ATM
              </button>
              <button
                type="button"
                className={cx(s.segBtn, props.strikeMode === 'fixed' && s.active)}
                aria-pressed={props.strikeMode === 'fixed'}
                onClick={() => props.onStrikeMode('fixed')}
                title="Pin the window to the session open's ATM"
              >
                Fixed
              </button>
            </div>

            <span className={s.label}>± Range:</span>
            <select
              className={s.spanSelect}
              aria-label="Strike range"
              value={props.span === null ? 'all' : String(props.span)}
              onChange={(e) => {
                const raw = e.currentTarget.value;
                props.onSpan(raw === 'all' ? null : Number(raw));
              }}
            >
              {SPANS.map((entry) => (
                <option
                  key={entry.label}
                  value={entry.value === null ? 'all' : String(entry.value)}
                >
                  {entry.label}
                </option>
              ))}
            </select>
          </>
        ) : (
          <>
            <span className={s.label}>Strikes:</span>
            <input
              className={s.strikeInput}
              type="number"
              inputMode="numeric"
              aria-label="Lowest strike"
              placeholder="from"
              value={props.custom.low}
              onChange={(e) => props.onCustom({ ...props.custom, low: e.currentTarget.value })}
            />
            <span className={s.dash} aria-hidden="true">
              –
            </span>
            <input
              className={s.strikeInput}
              type="number"
              inputMode="numeric"
              aria-label="Highest strike"
              placeholder="to"
              value={props.custom.high}
              onChange={(e) => props.onCustom({ ...props.custom, high: e.currentTarget.value })}
            />
          </>
        )}

        <span className={s.readout}>{windowLabel(props.strikeLow, props.strikeHigh)}</span>
      </div>
    </div>
  );
}
