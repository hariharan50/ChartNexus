import { useQuery } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';
import EChart from '$shared/charts/EChart';
import {
  buildVolatilitySkewOption,
  type SkewOverlay
} from '$shared/charts/options/volatility-skew';
import { useChartTheme } from '$shared/charts/theme/use-chart-theme';
import { isoDateIST, lastTradingDayIST } from '$shared/formatting/ist-clock';
import { cx } from '$shared/ui/cx';
import IconChart from '$shared/ui/icons/IconChart';
import IconEye from '$shared/ui/icons/IconEye';
import IconEyeOff from '$shared/ui/icons/IconEyeOff';
import ExpiryPicker from '../components/ExpiryPicker';
import HistoryMode, { type Mode } from '../components/HistoryMode';
import ReplayBar, { REPLAY_SPEEDS, type ReplaySpeed } from '../smart-oi/components/ReplayBar';
import TimeRangeSlider from '../components/TimeRangeSlider';
import {
  CALL_COLOR,
  clampWindow,
  clockLabel,
  coverageNote,
  csvFilename,
  dateLabel,
  fmtIv,
  fmtOi,
  freshnessLabel,
  getSkew,
  lowestIvStrike,
  nearestStrike,
  OI_INSTRUMENTS,
  overlayValues,
  prevTradingDay,
  PUT_COLOR,
  REFETCH_MS,
  sessionPositions,
  sessionTicks,
  skewBars,
  skewCsv,
  STALE_AFTER_MS,
  timeLabel,
  type AxisView,
  type SkewView
} from './volatility-skew-data';
import s from './route.module.css';
import type { Route } from './+types/route';

export const meta: Route.MetaFunction = () => [{ title: 'Volatility Skew · Options Lab' }];

/** The curve's own colour. Not call-green or put-red — it is neither side. */
const IV_COLOR = '#3b82f6';

/** How many prior sessions the T-Days control will overlay. */
const MAX_PRIOR_DAYS = 5;
const PRIOR_DAYS = [0, 1, 2, 3, 5] as const;

export default function VolatilitySkew() {
  const [instIdx, setInstIdx] = useState(0);
  const [dataMode, setDataMode] = useState<Mode>('live');
  const [date, setDate] = useState(lastTradingDayIST);
  const [axis, setAxis] = useState<AxisView>('strike');
  const [priorDays, setPriorDays] = useState(0);
  const [showLowest, setShowLowest] = useState(false);
  const [showRatio, setShowRatio] = useState(false);
  const [showIv, setShowIv] = useState(true);
  const [showCallOi, setShowCallOi] = useState(true);
  const [showPutOi, setShowPutOi] = useState(true);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  // `undefined` means "whatever the backend picks" — the nearest expiry.
  const [expiry, setExpiry] = useState<string | undefined>(undefined);
  /** Frame being shown, or -1 to follow live (far right of the track). */
  const [frameIdx, setFrameIdx] = useState(-1);
  /** Strike-slider handles, in index space; `null` until the ladder is known. */
  const [strikeRange, setStrikeRange] = useState<[number, number] | null>(null);
  const [replay, setReplay] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState<ReplaySpeed>(REPLAY_SPEEDS[1] ?? 2);

  const theme = useChartTheme();
  const instrument = OI_INSTRUMENTS[instIdx] ?? OI_INSTRUMENTS[0]!;

  function cycle(delta: number) {
    setInstIdx((current) => (current + delta + OI_INSTRUMENTS.length) % OI_INSTRUMENTS.length);
    // Neither index means anything on another instrument: the two sessions have
    // different capture counts and entirely different ladders.
    setFrameIdx(-1);
    setStrikeRange(null);
  }

  const historyDate = dataMode === 'historical' ? date : undefined;
  const query = useQuery<SkewView>({
    queryKey: ['options-lab', 'skew', instrument.symbol, dataMode, historyDate, expiry],
    queryFn: () => getSkew(instrument.symbol, { date: historyDate, expiry }),
    refetchInterval: dataMode === 'live' && !replay ? REFETCH_MS : false
  });

  const view = query.data;
  const frames = useMemo(() => view?.frames ?? [], [view]);
  const lastIdx = Math.max(0, frames.length - 1);
  const canScrub = frames.length >= 2;
  const shownIdx = frameIdx < 0 ? lastIdx : Math.min(frameIdx, lastIdx);
  const frame = frames[shownIdx];

  /**
   * The scrub track spans the trading session, not just what was recorded — so
   * a day whose ingest started at 1 pm draws as the late start it was rather
   * than being stretched across a morning it never saw. Same treatment as
   * Gamma Exposure.
   */
  const positions = useMemo(() => sessionPositions(view?.t ?? []), [view]);
  const ticks = useMemo(() => sessionTicks(), []);

  // -- prior sessions -------------------------------------------------------
  /** The N previous trading days, oldest last. */
  const priorDates = useMemo(() => {
    // The session on screen, which in Live mode is today — not the last
    // *completed* session. Counting back from yesterday would make "1 Day"
    // draw the day before the one the reader means.
    const base = historyDate ?? isoDateIST(0);
    const out: string[] = [];
    let cursor = base;
    for (let i = 0; i < MAX_PRIOR_DAYS; i++) {
      cursor = prevTradingDay(cursor);
      out.push(cursor);
    }
    return out;
  }, [historyDate]);

  const priorQueries = [
    usePriorSkew(instrument.symbol, priorDates[0], priorDays > 0),
    usePriorSkew(instrument.symbol, priorDates[1], priorDays > 1),
    usePriorSkew(instrument.symbol, priorDates[2], priorDays > 2),
    usePriorSkew(instrument.symbol, priorDates[3], priorDays > 3),
    usePriorSkew(instrument.symbol, priorDates[4], priorDays > 4)
  ];

  // -- the drawn window -----------------------------------------------------
  const strikeWindow = useMemo<[number, number]>(
    () =>
      clampWindow(strikeRange ?? [0, (view?.strikes.length ?? 1) - 1], view?.strikes.length ?? 0),
    [strikeRange, view]
  );

  const bars = useMemo(() => {
    if (!view || !frame) return [];
    return skewBars(view, frame, { window: strikeWindow, axis });
  }, [view, frame, strikeWindow, axis]);

  const lowest = useMemo(() => (showLowest ? lowestIvStrike(bars) : null), [showLowest, bars]);

  const overlays = useMemo<SkewOverlay[]>(() => {
    if (priorDays === 0 || !frame) return [];
    const todayAtm = frame.atm ?? nearestStrike(view?.strikes ?? [], frame.spot);
    return priorQueries.slice(0, priorDays).flatMap((prior, index) => {
      if (!prior.data) return [];
      const values = overlayValues(bars, prior.data, axis, todayAtm);
      if (values.every((value) => value === null)) return [];
      const label = priorDates[index];
      return [
        {
          id: `prior-${index}`,
          label: label ? `T−${index + 1} · ${label}` : `T−${index + 1}`,
          values
        }
      ];
    });
    // `priorQueries` is a fresh array each render; its data is what matters.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [priorDays, bars, axis, frame, view, priorDates, ...priorQueries.map((q) => q.data)]);

  const option = useMemo(
    () =>
      buildVolatilitySkewOption(
        {
          bars,
          spot: frame?.spot ?? 0,
          lowestIv: lowest,
          showIv,
          showCallOi,
          showPutOi,
          showRatio,
          overlays,
          ivColor: IV_COLOR,
          callColor: CALL_COLOR,
          putColor: PUT_COLOR,
          formatOi: (value: number) => fmtOi(value),
          formatIv: fmtIv
        },
        theme
      ),
    [bars, frame, lowest, showIv, showCallOi, showPutOi, showRatio, overlays, theme]
  );

  // -- replay ---------------------------------------------------------------
  useEffect(() => {
    if (!replay || !playing || !canScrub) return;
    const timer = window.setInterval(() => {
      setFrameIdx((current) => {
        const at = current < 0 ? lastIdx : current;
        if (at >= lastIdx) return lastIdx;
        return at + 1;
      });
    }, 600 / speed);
    return () => window.clearInterval(timer);
  }, [replay, playing, speed, canScrub, lastIdx]);

  // Leaving replay hands the page back to the live tail.
  useEffect(() => {
    if (replay) return;
    setPlaying(false);
  }, [replay]);

  // -- live clock -----------------------------------------------------------
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const updatedAt = query.dataUpdatedAt;
  const isStale = dataMode === 'live' && Boolean(updatedAt) && now - updatedAt > STALE_AFTER_MS;
  const asOf = frame ? timeLabel(frame.t) : '—';
  const note = view ? coverageNote(view) : null;

  function download() {
    if (bars.length === 0) return;
    const blob = new Blob([skewCsv(bars)], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = csvFilename(instrument.symbol, frame);
    link.click();
    URL.revokeObjectURL(url);
  }

  const strikeCount = view?.strikes.length ?? 0;

  return (
    <div className={s.page}>
      {query.isError ? (
        <div className={s.banner} role="alert">
          <span>Couldn’t load the volatility skew.</span>
          <button type="button" onClick={() => void query.refetch()}>
            Retry
          </button>
        </div>
      ) : !view && query.isPending ? (
        <div className={cx(s.panel, s.muted)}>Loading Volatility Skew…</div>
      ) : view && view.data_quality === 'empty' ? (
        // The mode toggle rides along so a picked date that turns up empty is
        // not a dead end — the reader can change the date or return to Live.
        <div className={cx(s.panel, s.emptyPanel)}>
          <HistoryMode mode={dataMode} date={date} onMode={setDataMode} onDate={setDate} />
          <p className={s.muted}>
            {dataMode === 'historical'
              ? 'No session archived for that date.'
              : 'No chain captures recorded for today yet — the skew fills in as the ingest worker captures the chain.'}
          </p>
        </div>
      ) : view && frame ? (
        <div className={cx(s.layout, !sidebarOpen && s.collapsed)}>
          {/* LEFT SIDEBAR */}
          {sidebarOpen ? (
            <aside className={s.sidebar}>
              <section className={s.panel}>
                <div className={s.panelHead}>
                  <h2 className={s.pTitle}>Settings</h2>
                  <button
                    type="button"
                    className={s.collapseBtn}
                    aria-label="Collapse settings"
                    aria-expanded={true}
                    onClick={() => setSidebarOpen(false)}
                  >
                    «
                  </button>
                </div>

                <div className={s.instrument}>
                  <span className={s.badge}>{instrument.badge}</span>
                  <span className={s.short}>{instrument.short}</span>
                  <span className={s.cyclers}>
                    <button type="button" aria-label="Previous" onClick={() => cycle(-1)}>
                      ‹
                    </button>
                    <button type="button" aria-label="Next" onClick={() => cycle(1)}>
                      ›
                    </button>
                  </span>
                </div>

                <HistoryMode mode={dataMode} date={date} onMode={setDataMode} onDate={setDate} />

                <ExpiryPicker
                  instrument={instrument.symbol}
                  value={expiry}
                  onChange={setExpiry}
                  resolved={view.expiry_date}
                  archiveBound
                  dataQuality={view?.data_quality}
                />

                <p className={s.subLabel}>X-Axis View</p>
                <div className={s.segRow} role="tablist" aria-label="X-axis view">
                  <button
                    type="button"
                    role="tab"
                    aria-selected={axis === 'strike'}
                    className={cx(s.seg, axis === 'strike' && s.active)}
                    onClick={() => setAxis('strike')}
                  >
                    Strike
                  </button>
                  <button
                    type="button"
                    role="tab"
                    aria-selected={axis === 'atm'}
                    className={cx(s.seg, axis === 'atm' && s.active)}
                    onClick={() => setAxis('atm')}
                    title="Position on the ladder relative to the money"
                  >
                    ATM+−
                  </button>
                </div>

                <p className={s.subLabel}>Previous Days (T-Days)</p>
                <select
                  className={s.selectNative}
                  value={priorDays}
                  aria-label="Previous days"
                  onChange={(e) => setPriorDays(Number(e.currentTarget.value))}
                >
                  {PRIOR_DAYS.map((days) => (
                    <option key={days} value={days}>
                      {days === 0 ? '0 Days' : `${days} Day${days === 1 ? '' : 's'}`}
                    </option>
                  ))}
                </select>

                <Switch label="Show Lowest IV" on={showLowest} onChange={setShowLowest} />
                <Switch
                  label="Vol Ratio"
                  hint="Call IV ÷ put IV at each strike — above 1, the calls there are bid richer than the puts."
                  on={showRatio}
                  onChange={setShowRatio}
                />
              </section>
            </aside>
          ) : (
            <button
              type="button"
              className={s.restore}
              aria-label="Show settings"
              aria-expanded={false}
              onClick={() => setSidebarOpen(true)}
            >
              »
            </button>
          )}

          {/* RIGHT MAIN */}
          <div className={s.main}>
            <section className={s.panel}>
              <div className={s.chartTop}>
                <div className={s.chartTopLeft}>
                  <h2 className={s.pTitle}>
                    <span className={s.ico} aria-hidden="true">
                      <IconChart />
                    </span>{' '}
                    Volatility Skew
                  </h2>

                  <div className={s.legend}>
                    <Toggle
                      label="IV"
                      color={IV_COLOR}
                      on={showIv}
                      onToggle={() => setShowIv((v) => !v)}
                    />
                    <Toggle
                      label="Call OI"
                      color={CALL_COLOR}
                      on={showCallOi}
                      onToggle={() => setShowCallOi((v) => !v)}
                    />
                    <Toggle
                      label="Put OI"
                      color={PUT_COLOR}
                      on={showPutOi}
                      onToggle={() => setShowPutOi((v) => !v)}
                    />
                  </div>
                </div>

                <div className={s.chartTopRight}>
                  <Switch
                    label="Replay"
                    on={replay}
                    onChange={setReplay}
                    disabled={!canScrub}
                    inline
                  />
                  <span className={cx(s.live, isStale && s.stale)}>
                    <span
                      className={cx(s.dot, dataMode === 'live' && query.isFetching && s.pulse)}
                    />
                    <span>
                      {dataMode === 'live' ? (
                        <>
                          {dateLabel(now)}, {clockLabel(now)} IST
                        </>
                      ) : (
                        <>Archived · {date}</>
                      )}
                    </span>
                    {dataMode === 'live' ? (
                      <>
                        <span className={s.sep} aria-hidden="true">
                          ·
                        </span>
                        <span>updated {freshnessLabel(updatedAt, now)}</span>
                      </>
                    ) : null}
                  </span>
                  <button
                    type="button"
                    className={s.download}
                    onClick={download}
                    title="Download the drawn curve as CSV"
                  >
                    ↓ CSV
                  </button>
                </div>
              </div>

              {bars.length === 0 ? (
                <p className={s.empty}>No strikes in the selected range.</p>
              ) : (
                <EChart
                  option={option}
                  resetKey={`${instrument.symbol}-${axis}-${dataMode}-${historyDate ?? ''}`}
                  className={s.chart}
                />
              )}

              {replay ? (
                <ReplayBar
                  head={shownIdx}
                  total={frames.length}
                  playing={playing}
                  speed={speed}
                  at={frame.t}
                  onHead={(head) => setFrameIdx(head === lastIdx ? -1 : head)}
                  onPlaying={setPlaying}
                  onSpeed={setSpeed}
                  onExit={() => setReplay(false)}
                />
              ) : (
                <div className={s.sliderRow}>
                  <span className={s.sliderLabel}>Time</span>
                  <button
                    type="button"
                    className={s.reset}
                    onClick={() => setFrameIdx(-1)}
                    disabled={frameIdx < 0}
                  >
                    Reset
                  </button>
                  <span className={s.end}>9:15 am</span>
                  <TimeRangeSlider
                    min={0}
                    max={lastIdx}
                    single
                    openIndex={0}
                    nowIndex={shownIdx}
                    disabled={!canScrub}
                    nowLabel={asOf}
                    positions={positions}
                    ticks={ticks}
                    onOpenChange={() => undefined}
                    onNowChange={(index) => setFrameIdx(index === lastIdx ? -1 : index)}
                  />
                  <span className={s.end}>{asOf}</span>
                </div>
              )}

              <div className={s.sliderRow}>
                <span className={s.sliderLabel}>Strike</span>
                <button
                  type="button"
                  className={s.reset}
                  onClick={() => setStrikeRange(null)}
                  disabled={strikeRange === null}
                >
                  Reset
                </button>
                <span className={s.end}>{view.strikes[strikeWindow[0]] ?? '—'}</span>
                <TimeRangeSlider
                  min={0}
                  max={Math.max(0, strikeCount - 1)}
                  openIndex={strikeWindow[0]}
                  nowIndex={strikeWindow[1]}
                  disabled={strikeCount < 2}
                  openLabel={String(view.strikes[strikeWindow[0]] ?? '')}
                  nowLabel={String(view.strikes[strikeWindow[1]] ?? '')}
                  onOpenChange={(index) => setStrikeRange([index, strikeWindow[1]])}
                  onNowChange={(index) => setStrikeRange([strikeWindow[0], index])}
                />
                <span className={s.end}>{view.strikes[strikeWindow[1]] ?? '—'}</span>
              </div>

              <p className={s.caption}>
                The curve is the out-of-the-money volatility at each strike — puts below spot, calls
                above — over the open interest held on each side. Spot is dotted.
                {note ? ` ${note}` : ''}
              </p>
            </section>
          </div>
        </div>
      ) : null}
    </div>
  );
}

/** One prior session's payload, fetched only once its overlay is asked for. */
function usePriorSkew(symbol: string, date: string | undefined, enabled: boolean) {
  return useQuery<SkewView>({
    queryKey: ['options-lab', 'skew', symbol, 'prior', date],
    queryFn: () => getSkew(symbol, { date }),
    enabled: enabled && date !== undefined,
    // A closed session never changes; there is nothing to poll for.
    staleTime: Infinity
  });
}

/** A labelled on/off switch — the app's canonical one. */
function Switch({
  label,
  hint,
  on,
  onChange,
  disabled,
  inline
}: {
  label: string;
  hint?: string;
  on: boolean;
  onChange: (next: boolean) => void;
  disabled?: boolean;
  inline?: boolean;
}) {
  return (
    <label className={cx(s.toggle, inline && s.toggleInline, disabled && s.toggleOff)}>
      <span>
        {label}
        {hint ? (
          <span className={s.info} title={hint} aria-hidden="true">
            ⓘ
          </span>
        ) : null}
      </span>
      <input
        type="checkbox"
        checked={on}
        disabled={disabled}
        onChange={(e) => onChange(e.currentTarget.checked)}
      />
      <span className={cx(s.switch, on && s.on)}>
        <span className={s.knob} />
      </span>
    </label>
  );
}

/** An eye chip over the chart, showing and hiding one series. */
function Toggle({
  label,
  color,
  on,
  onToggle
}: {
  label: string;
  color: string;
  on: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      className={cx(s.entry, !on && s.off)}
      aria-pressed={on}
      onClick={onToggle}
    >
      <span className={s.eye} aria-hidden="true">
        {on ? <IconEye /> : <IconEyeOff />}
      </span>
      <span className={s.swatch} style={{ background: color }} />
      <span className={s.label}>{label}</span>
    </button>
  );
}
