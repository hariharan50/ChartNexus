import { useQuery } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo, useState } from 'react';
import EChart from '$shared/charts/EChart';
import { buildGammaExposureOption, type GexMarker } from '$shared/charts/options/gamma-exposure';
import { useChartTheme } from '$shared/charts/theme/use-chart-theme';
import { cx } from '$shared/ui/cx';
import IconChart from '$shared/ui/icons/IconChart';
import IconChevronDown from '$shared/ui/icons/IconChevronDown';
import IconEye from '$shared/ui/icons/IconEye';
import IconEyeOff from '$shared/ui/icons/IconEyeOff';
import { lastTradingDayIST } from '$shared/formatting/ist-clock';
import GexLevels from './components/GexLevels';
import GexReadout from './components/GexReadout';
import HistoryMode, { type Mode } from '../components/HistoryMode';
import {
  csvFilename,
  expiryLabel,
  fmtGex,
  frameBars,
  frameLevels,
  getGex,
  gexCsv,
  LAYOUTS,
  readoutRows,
  STRIKE_FILTERS,
  type GexLayout,
  type GexView
} from './gex-data';
import {
  CALL_COLOR,
  clockLabel,
  dateLabel,
  freshnessLabel,
  inferStep,
  OI_INSTRUMENTS,
  PUT_COLOR,
  REFETCH_MS,
  sessionPositions,
  sessionTicks,
  STALE_AFTER_MS,
  timeLabel,
  withinWindow
} from '../open-interest/oi-data';
import TimeRangeSlider from '../components/TimeRangeSlider';
import s from './route.module.css';
import type { Route } from './+types/route';

export const meta: Route.MetaFunction = () => [{ title: 'Gamma Exposure · Options Lab' }];

/**
 * Marker colours, and the vertical slot each chip occupies.
 *
 * Slot 0 belongs to spot, which is drawn by the chart builder itself. The four
 * derived levels stack beneath it in the order they are read: where the book
 * turns, then where the profile turns, then the two walls.
 */
const LEVEL_STYLE: Record<string, { color: string; slot: number }> = {
  gammaFlip: { color: '#22d3ee', slot: 1 },
  netCross: { color: '#f59e0b', slot: 2 },
  callWall: { color: CALL_COLOR, slot: 3 },
  putWall: { color: PUT_COLOR, slot: 4 }
};

const LEVEL_COLORS: Record<string, string> = Object.fromEntries(
  Object.entries(LEVEL_STYLE).map(([id, style]) => [id, style.color])
);

/** Which sidebar toggle governs which levels. */
const WALL_IDS = ['callWall', 'putWall'];
const FLIP_IDS = ['gammaFlip', 'netCross'];

export default function GammaExposure() {
  const [instIdx, setInstIdx] = useState(0);
  const [dataMode, setDataMode] = useState<Mode>('live');
  const [date, setDate] = useState(lastTradingDayIST);
  const [layout, setLayout] = useState<GexLayout>('horizontal');
  const [strikeFilter, setStrikeFilter] = useState<'all' | number>(10);
  const [showWalls, setShowWalls] = useState(false);
  const [showFlip, setShowFlip] = useState(false);
  const [showNet, setShowNet] = useState(true);
  const [showAbs, setShowAbs] = useState(true);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  /** Frame being shown, or -1 to follow live (far right of the track). */
  const [frameIdx, setFrameIdx] = useState(-1);

  const theme = useChartTheme();
  const instrument = OI_INSTRUMENTS[instIdx] ?? OI_INSTRUMENTS[0]!;

  function cycle(delta: number) {
    setInstIdx((current) => (current + delta + OI_INSTRUMENTS.length) % OI_INSTRUMENTS.length);
    // A frame index means nothing on another instrument: the two sessions have
    // different capture counts, so index 40 is a different time on each.
    setFrameIdx(-1);
  }

  const historyDate = dataMode === 'historical' ? date : undefined;
  const query = useQuery<GexView>({
    queryKey: ['options-lab', 'gex', instrument.symbol, dataMode, historyDate],
    queryFn: () => getGex(instrument.symbol, { date: historyDate }),
    refetchInterval: dataMode === 'live' ? REFETCH_MS : false
  });

  const view = query.data;
  const frames = useMemo(() => view?.frames ?? [], [view]);
  const lastIdx = Math.max(0, frames.length - 1);
  const canScrub = frames.length >= 2;
  const shownIdx = frameIdx < 0 ? lastIdx : Math.min(frameIdx, lastIdx);
  const frame = frames[shownIdx];

  /**
   * The scrub track spans the trading session, not just what was recorded.
   *
   * Index positioning stretches whatever frames exist across the full width,
   * so a day whose ingest started at 1 pm draws a track running 1 pm to 3 pm
   * and reads as a complete session. Here the track is always 9:15 to 3:30 and
   * the frames sit at their real clock positions, so a late start is visibly a
   * late start: the handle simply cannot travel into the morning.
   */
  const positions = useMemo(() => sessionPositions(view?.t ?? []), [view]);
  const ticks = useMemo(() => sessionTicks(), []);
  /** More than one tick of the track missing at the left — worth explaining. */
  const startsLate = (positions[0] ?? 0) > 1;

  // -- the drawn window -----------------------------------------------------
  /**
   * Centred on the *shown* frame's ATM, never the payload's.
   *
   * Spot moves through a session, so anchoring to the newest ATM while drawing
   * an 10:30 frame slides the window off to one side of that frame's profile —
   * the same bug the Open Interest page documents.
   */
  const bars = useMemo(() => {
    if (!view || !frame) return [];
    const anchor = frame.atm ?? frame.spot;
    const visible = withinWindow(
      view.strikes,
      anchor,
      inferStep(view.strikes),
      strikeFilter === 'all' ? 0 : strikeFilter
    );
    return frameBars(view.strikes, frame, new Set(visible));
  }, [view, frame, strikeFilter]);

  const levels = useMemo(() => frameLevels(frame), [frame]);

  /** The ids currently drawn — shared by the chart and the levels row. */
  const shownIds = useMemo(() => {
    const ids = new Set<string>();
    if (showWalls) for (const id of WALL_IDS) ids.add(id);
    if (showFlip) for (const id of FLIP_IDS) ids.add(id);
    return ids;
  }, [showWalls, showFlip]);

  const markers = useMemo<GexMarker[]>(
    () =>
      levels.flatMap((level) => {
        const style = LEVEL_STYLE[level.id];
        if (!style || level.strike === null || !shownIds.has(level.id)) return [];
        return [
          {
            id: level.id,
            label: level.label,
            strike: level.strike,
            color: style.color,
            slot: style.slot
          }
        ];
      }),
    [levels, shownIds]
  );

  const option = useMemo(
    () =>
      buildGammaExposureOption(
        {
          bars,
          layout,
          spot: frame?.spot ?? 0,
          markers,
          showNet,
          showAbs,
          callColor: CALL_COLOR,
          putColor: PUT_COLOR,
          formatGex: fmtGex
        },
        theme
      ),
    [bars, layout, frame, markers, showNet, showAbs, theme]
  );

  // -- hovered strike -------------------------------------------------------
  /** Index into `bars`, or `null` when the pointer is off the plot. */
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);
  const onAxisHover = useCallback((index: number | null) => setHoverIdx(index), []);

  /**
   * What the panel falls back to: the strike nearest spot.
   *
   * A readout that is blank until hovered reads as a broken box. The strike
   * beside spot is also the one a reader would have pointed at first, so the
   * fallback is rarely the wrong guess.
   */
  const defaultIdx = useMemo(() => {
    if (bars.length === 0 || !frame) return null;
    let best = 0;
    let gap = Infinity;
    bars.forEach((bar, i) => {
      const distance = Math.abs(bar.strike - frame.spot);
      if (distance < gap) {
        gap = distance;
        best = i;
      }
    });
    return best;
  }, [bars, frame]);

  // A stale hover index outlives the bars it pointed into — the strike filter
  // and the time scrub both rebuild `bars` underneath it.
  const activeIdx = hoverIdx !== null && hoverIdx < bars.length ? hoverIdx : defaultIdx;
  const activeBar = activeIdx === null ? undefined : bars[activeIdx];

  const readout = useMemo(
    () =>
      activeBar
        ? readoutRows(activeBar, {
            layout,
            showNet,
            showAbs,
            callColor: CALL_COLOR,
            putColor: PUT_COLOR,
            absColor: theme.marker
          })
        : [],
    [activeBar, layout, showNet, showAbs, theme.marker]
  );

  // -- live clock -----------------------------------------------------------
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(t);
  }, []);

  const updatedAt = query.dataUpdatedAt;
  const isStale = Boolean(updatedAt) && now - updatedAt > STALE_AFTER_MS;
  const asOf = frame ? timeLabel(frame.t) : '—';

  function download() {
    if (!view) return;
    const blob = new Blob([gexCsv(bars, frame)], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = csvFilename(view.symbol, frame);
    link.click();
    // Without this the blob is pinned for the life of the document, and this
    // page is one people leave open all session.
    URL.revokeObjectURL(url);
  }

  return (
    <div className={s.page}>
      {query.isError ? (
        <div className={s.banner} role="alert">
          <span>Couldn’t load gamma exposure.</span>
          <button type="button" onClick={() => void query.refetch()}>
            Retry
          </button>
        </div>
      ) : !view && query.isPending ? (
        <div className={cx(s.panel, s.muted)}>Loading Gamma Exposure…</div>
      ) : view && view.data_quality === 'empty' ? (
        // The mode toggle rides along so a picked date that turns up empty is
        // not a dead end — the reader can change the date or return to Live.
        <div className={cx(s.panel, s.emptyPanel)}>
          <HistoryMode mode={dataMode} date={date} onMode={setDataMode} onDate={setDate} />
          <p className={s.muted}>
            {dataMode === 'historical'
              ? 'No session archived for that date.'
              : 'No gamma data recorded for today yet — the profile fills in as the ingest worker captures the chain.'}
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

                <p className={s.subLabel}>Expiry</p>
                <div className={s.select}>
                  <span>{expiryLabel(view.expiry_date)}</span>
                  <span className={s.caret} aria-hidden="true">
                    <IconChevronDown />
                  </span>
                </div>

                <p className={s.subLabel}>Chart</p>
                <div className={s.layoutRow}>
                  {LAYOUTS.map((entry) => (
                    <button
                      key={entry.value}
                      type="button"
                      className={cx(s.seg, layout === entry.value && s.active)}
                      aria-pressed={layout === entry.value}
                      onClick={() => setLayout(entry.value)}
                    >
                      {entry.label}
                    </button>
                  ))}
                </div>

                <p className={s.subLabel}>Strikes above-below ATM</p>
                <div className={s.filterRow}>
                  {STRIKE_FILTERS.map((filter) => (
                    <button
                      key={filter.label}
                      type="button"
                      className={cx(s.chip, strikeFilter === filter.value && s.active)}
                      aria-pressed={strikeFilter === filter.value}
                      onClick={() => setStrikeFilter(filter.value)}
                    >
                      {filter.label}
                    </button>
                  ))}
                </div>

                <Toggle label="Show Walls" on={showWalls} onChange={setShowWalls} />
                <Toggle label="Show Flip" on={showFlip} onChange={setShowFlip} />
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
            <section className={cx(s.panel, s.chartPanel)}>
              <div className={s.chartTop}>
                <h2 className={s.pTitle}>
                  <span className={s.ico} aria-hidden="true">
                    <IconChart />
                  </span>{' '}
                  Gamma Exposure
                </h2>

                <div className={s.headline}>
                  <span>
                    Net GEX{' '}
                    <strong className={frame.net_total >= 0 ? s.up : s.down}>
                      {fmtGex(frame.net_total)}
                    </strong>
                  </span>
                  <span>
                    ABS GEX <strong>{fmtGex(frame.abs_total)}</strong>
                  </span>
                </div>

                <div className={s.chartTopRight}>
                  <span className={cx(s.live, isStale && s.stale)}>
                    <span className={cx(s.dot, query.isFetching && s.pulse)} />
                    <span>
                      {dateLabel(now)}, {clockLabel(now)} IST
                    </span>
                    <span className={s.sep} aria-hidden="true">
                      ·
                    </span>
                    <span>updated {freshnessLabel(updatedAt, now)}</span>
                  </span>
                  <button
                    type="button"
                    className={s.download}
                    onClick={download}
                    title="Download the visible strikes as CSV"
                  >
                    ↓ CSV
                  </button>
                </div>
              </div>

              {/* The drawn window, in words. The chart is a canvas, so without
                  this the strike filter gives no readable confirmation of what
                  it did — and this page's filter also decides what the CSV
                  button exports. */}
              <p className={s.range}>
                {bars.length > 0
                  ? `Showing ${bars.length} strikes · ${bars[0]!.strike} – ${bars[bars.length - 1]!.strike}`
                  : 'Showing no strikes'}
                <span className={s.sep} aria-hidden="true">
                  {' · '}
                </span>
                {view.strikes.length} on the axis
              </p>

              {/* Series toggles. Real buttons, not decoration: hiding a series
                  drops it from the option so the other one's axis rescales to
                  fill the plot. */}
              <div className={s.seriesRow}>
                <SeriesToggle label="Net GEX (Cr)" on={showNet} onChange={setShowNet} />
                <SeriesToggle label="ABS GEX (Cr)" on={showAbs} onChange={setShowAbs} />
              </div>

              {bars.length === 0 ? (
                <p className={s.empty}>No strikes in this window.</p>
              ) : (
                <div className={s.plotRow}>
                  <EChart
                    option={option}
                    // The axes swap wholesale between layouts and the series list
                    // changes with the toggles; a merge would leave the previous
                    // shape's axes and series behind.
                    resetKey={`${layout}-${showNet}-${showAbs}`}
                    className={s.chart}
                    onAxisHover={onAxisHover}
                  />
                  <GexReadout
                    strike={activeBar?.strike ?? null}
                    rows={readout}
                    isDefault={hoverIdx === null}
                  />
                </div>
              )}

              <GexLevels levels={levels} shown={shownIds} colors={LEVEL_COLORS} />

              {/* time scrub */}
              <div className={s.sliderRow}>
                <button
                  type="button"
                  className={s.reset}
                  onClick={() => setFrameIdx(-1)}
                  disabled={!canScrub}
                >
                  Reset
                </button>
                {/* The bell, not the first capture. The track is the session,
                    and where the recording actually starts is the caption's
                    job — saying it here would label the left edge with a time
                    the handle can never reach. */}
                <span className={s.end}>
                  <span className={s.endCaption}>Session</span>
                  <span>9:15 am</span>
                </span>
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
                <span className={s.end}>
                  <span className={s.endCaption}>As of</span>
                  <span>{asOf}</span>
                </span>
              </div>

              <p className={s.caption}>
                Exposure is in crore per 1% move in spot, from the dealer’s side of the book — call
                gamma positive, put gamma negative. Positive net means dealers hedge against the
                move and damp it; negative means they hedge with it.{' '}
                {/* Open interest, not legs. The IV solver fails on strikes
                    nobody holds, so a leg count reported a fifth of the book
                    missing when the exposure that missing fifth carried was
                    nil — see `gex_math.strike_profile`. */}
                {view.iv_coverage < 0.995
                  ? `The broker quoted no volatility on ${Math.round((1 - view.iv_coverage) * 100)}% of open interest, which contributes nothing to these figures.`
                  : ''}{' '}
                {/* Names the empty stretch at the left of the track. Gamma has no
                    reconstructable open — restating open interest from the day-change
                    field needs no spot, and gamma does — so a late ingest start leaves
                    a real hole rather than an estimated morning. */}
                The timeline spans the 9:15 am – 3:30 pm session
                {startsLate
                  ? `, but recording only began at ${timeLabel(view.open_ts)} — there is no earlier frame to scrub to.`
                  : `, recorded from ${timeLabel(view.open_ts)}.`}
              </p>
            </section>
          </div>
        </div>
      ) : null}
    </div>
  );
}

/** A sidebar switch, styled as the Open Interest page's "Show Lot". */
function Toggle({
  label,
  on,
  onChange
}: {
  label: string;
  on: boolean;
  onChange: (next: boolean) => void;
}) {
  return (
    <label className={s.toggle}>
      <span>{label}</span>
      <input type="checkbox" checked={on} onChange={(e) => onChange(e.currentTarget.checked)} />
      <span className={cx(s.switch, on && s.on)}>
        <span className={s.knob} />
      </span>
    </label>
  );
}

/** An eye chip over the chart, showing and hiding one series. */
function SeriesToggle({
  label,
  on,
  onChange
}: {
  label: string;
  on: boolean;
  onChange: (next: boolean) => void;
}) {
  return (
    <button
      type="button"
      className={cx(s.seriesChip, !on && s.off)}
      aria-pressed={on}
      onClick={() => onChange(!on)}
    >
      <span className={s.eye} aria-hidden="true">
        {on ? <IconEye /> : <IconEyeOff />}
      </span>
      {label}
    </button>
  );
}
