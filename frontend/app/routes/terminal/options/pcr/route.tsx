import { useQuery } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { SeriesLine } from '$shared/charts/options/multi-series';
import { cx } from '$shared/ui/cx';
import IconChart from '$shared/ui/icons/IconChart';
import IconChevronDown from '$shared/ui/icons/IconChevronDown';
import SeriesChart from '../components/SeriesChart';
import { CALL_COLOR, PUT_COLOR } from '../open-interest/oi-data';
import {
  bucketIndices,
  DEFAULT_TIMEFRAME,
  expiryLabel,
  fmtOi,
  fmtPrice,
  fmtRatio,
  getPcrSeries,
  pick,
  REFETCH_MS,
  timeLabel,
  TIMEFRAMES,
  type PcrSeriesView,
  type Timeframe
} from './pcr-data';
import s from './route.module.css';
import type { Route } from './+types/route';

export const meta: Route.MetaFunction = () => [{ title: 'Put-Call Ratio · Options Lab' }];

const INSTRUMENTS = [
  { short: 'NIFTY', badge: '50', symbol: 'NIFTY' },
  { short: 'SENSEX', badge: 'BSE', symbol: 'SENSEX' },
  { short: 'BANKNIFTY', badge: 'BNK', symbol: 'BANKNIFTY' }
];

/** Charts sharing this group share one crosshair. */
const CHART_GROUP = 'pcr';

/** How long a full replay sweep takes, whatever the session's length. */
const REPLAY_MS = 15_000;

export default function PutCallRatio() {
  const [instIdx, setInstIdx] = useState(0);
  const [timeframe, setTimeframe] = useState<Timeframe>(DEFAULT_TIMEFRAME);

  const instrument = INSTRUMENTS[instIdx] ?? INSTRUMENTS[0]!;

  const query = useQuery<PcrSeriesView>({
    queryKey: ['options-lab', 'pcr-series', instrument.symbol],
    queryFn: () => getPcrSeries(instrument.symbol),
    refetchInterval: REFETCH_MS
  });

  const view = query.data;

  // -- resampling -----------------------------------------------------------
  // Every array below is derived from one payload; changing the timeframe never
  // refetches, which is the whole reason the endpoint sends the raw cadence.
  const kept = useMemo(() => bucketIndices(view?.t ?? [], timeframe), [view, timeframe]);
  const times = useMemo(() => pick(view?.t ?? [], kept).map(timeLabel), [view, kept]);
  const futures = useMemo(() => pick(view?.fut ?? [], kept), [view, kept]);

  const pcrLines = useMemo<SeriesLine[]>(
    () => [
      {
        id: 'pcr',
        label: 'Put-Call Ratio',
        color: '#3b82f6',
        values: pick(view?.pcr ?? [], kept)
      }
    ],
    [view, kept]
  );

  const changeLines = useMemo<SeriesLine[]>(
    () => [
      {
        id: 'call-chg',
        label: 'Call OI Change',
        color: CALL_COLOR,
        values: pick(view?.call_oi_chg ?? [], kept)
      },
      {
        id: 'put-chg',
        label: 'Put OI Change',
        color: PUT_COLOR,
        values: pick(view?.put_oi_chg ?? [], kept)
      }
    ],
    [view, kept]
  );

  const totalLines = useMemo<SeriesLine[]>(
    () => [
      {
        id: 'call-oi',
        label: 'Call OI',
        color: CALL_COLOR,
        values: pick(view?.call_oi ?? [], kept)
      },
      { id: 'put-oi', label: 'Put OI', color: PUT_COLOR, values: pick(view?.put_oi ?? [], kept) }
    ],
    [view, kept]
  );

  // -- replay ---------------------------------------------------------------
  const { head, playing, toggle } = useReplay(times.length);

  // -- live clock -----------------------------------------------------------
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(t);
  }, []);
  const clock = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Asia/Kolkata',
    day: 'numeric',
    month: 'short',
    hour: 'numeric',
    minute: '2-digit',
    second: '2-digit',
    hour12: true
  })
    .format(now)
    .toLowerCase();

  return (
    <div className={s.page}>
      {query.isError ? (
        <div className={s.banner} role="alert">
          <span>Couldn’t load the put-call ratio.</span>
          <button type="button" onClick={() => void query.refetch()}>
            Retry
          </button>
        </div>
      ) : !view && query.isPending ? (
        <div className={cx(s.panel, s.muted)}>Loading Put-Call Ratio…</div>
      ) : view ? (
        <div className={s.layout}>
          {/* LEFT SIDEBAR */}
          <aside className={s.sidebar}>
            <section className={s.panel}>
              <h2 className={s.pTitle}>Settings</h2>

              <div className={s.instrument}>
                <span className={s.badge}>{instrument.badge}</span>
                <span className={s.short}>{instrument.short}</span>
                <span className={s.cyclers}>
                  <button
                    type="button"
                    aria-label="Previous"
                    onClick={() =>
                      setInstIdx((i) => (i - 1 + INSTRUMENTS.length) % INSTRUMENTS.length)
                    }
                  >
                    ‹
                  </button>
                  <button
                    type="button"
                    aria-label="Next"
                    onClick={() => setInstIdx((i) => (i + 1) % INSTRUMENTS.length)}
                  >
                    ›
                  </button>
                </span>
              </div>

              <p className={s.subLabel}>Select Mode</p>
              <div className={s.modeGrid}>
                <button type="button" className={cx(s.seg, s.active)}>
                  Live
                </button>
                <button
                  type="button"
                  className={s.seg}
                  disabled
                  title="Historical mode coming soon"
                >
                  Historical
                </button>
              </div>

              <p className={s.subLabel}>Expiry</p>
              <div className={s.select}>
                <span>{expiryLabel(view.expiry_date)}</span>
                <span className={s.caret} aria-hidden="true">
                  <IconChevronDown />
                </span>
              </div>

              <p className={s.subLabel}>Timeframe</p>
              <select
                className={s.selectNative}
                aria-label="Timeframe"
                value={timeframe}
                onChange={(e) => setTimeframe(e.currentTarget.value as Timeframe)}
              >
                {TIMEFRAMES.map((option) => (
                  <option key={option.value} value={option.value} disabled={option.disabled}>
                    {option.label}
                  </option>
                ))}
              </select>
            </section>
          </aside>

          {/* RIGHT MAIN */}
          <div className={s.main}>
            <div className={s.topBar}>
              <div className={s.topLeft}>
                <button
                  type="button"
                  className={s.dayWise}
                  disabled
                  title="Needs history across sessions, which the archive does not keep yet"
                >
                  Day-wise PCR →
                </button>
              </div>
              <div className={s.topRight}>
                <label className={s.replay}>
                  <span>Replay</span>
                  <input
                    type="checkbox"
                    checked={playing}
                    onChange={toggle}
                    disabled={times.length < 2}
                  />
                  <span className={cx(s.switch, playing && s.on)}>
                    <span className={s.knob} />
                  </span>
                </label>
                <span className={s.live}>
                  <span className={cx(s.dot, query.isFetching && s.pulse)} />
                  {clock} IST
                </span>
              </div>
            </div>

            <SeriesChart
              title="Put-Call Ratio"
              subtitle="Put open interest divided by call — above 1, puts outweigh calls."
              icon={<IconChart />}
              valueAxisName="PCR"
              referenceLine={{ value: 1, label: 'PCR 1' }}
              lines={pcrLines}
              times={times}
              futures={futures}
              formatValue={fmtRatio}
              formatPrice={fmtPrice}
              group={CHART_GROUP}
              head={head}
            />
            <SeriesChart
              title="OI Change (Call vs Put)"
              subtitle="Positions added or closed on each side since the 9:15 open."
              icon={<IconChart />}
              valueAxisName="OI change"
              lines={changeLines}
              times={times}
              futures={futures}
              formatValue={fmtOi}
              formatPrice={fmtPrice}
              group={CHART_GROUP}
              head={head}
            />
            <SeriesChart
              title="Total OI (Call vs Put)"
              subtitle="Total open interest standing on each side of the chain."
              icon={<IconChart />}
              valueAxisName="Open interest"
              lines={totalLines}
              times={times}
              futures={futures}
              formatValue={fmtOi}
              formatPrice={fmtPrice}
              group={CHART_GROUP}
              head={head}
            />

            <p className={s.caption}>
              {view.data_quality === 'empty'
                ? 'No snapshots recorded for today yet — the series fills in as the ingest worker captures them.'
                : view.open_is_estimated
                  ? `The ${timeLabel(view.t[0]!)} baseline is derived from the day’s OI change; recorded history starts at ${timeLabel(view.t[1] ?? view.t[0]!)}.`
                  : `Recorded from ${timeLabel(view.t[0]!)}, resampled to ${timeframe}.`}
            </p>
          </div>
        </div>
      ) : null}
    </div>
  );
}

/**
 * The replay sweep: a head index walking from the open to the last point.
 *
 * `undefined` means live — every point drawn. Toggling on starts at the open and
 * advances on a wall-clock schedule, so the sweep lasts the same ~15 seconds on
 * a 60 Hz and a 144 Hz display rather than running twice as fast on the latter.
 */
function useReplay(length: number) {
  const [head, setHead] = useState<number | undefined>(undefined);
  const [playing, setPlaying] = useState(false);
  const frame = useRef<number>(0);

  const stop = useCallback(() => {
    cancelAnimationFrame(frame.current);
    setPlaying(false);
    setHead(undefined);
  }, []);

  useEffect(() => {
    if (!playing || length < 2) return;

    // Someone who has asked for less motion should still get the answer, just
    // not the animation — an animated sweep is precisely what this setting is
    // about.
    if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) {
      setHead(length - 1);
      return;
    }

    const started = performance.now();
    const tick = (at: number) => {
      const progress = Math.min(1, (at - started) / REPLAY_MS);
      setHead(Math.round(progress * (length - 1)));
      if (progress < 1) frame.current = requestAnimationFrame(tick);
      else setPlaying(false);
    };
    frame.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame.current);
  }, [playing, length]);

  const toggle = useCallback(() => {
    if (playing) stop();
    else {
      setHead(0);
      setPlaying(true);
    }
  }, [playing, stop]);

  // A finished sweep leaves the head at the end, which reads as paused-at-now.
  // Anything that changes the series length — a poll, a timeframe switch —
  // should hand the charts back to live rather than freeze them mid-history.
  useEffect(() => {
    if (!playing) setHead(undefined);
  }, [length, playing]);

  return { head, playing, toggle };
}
