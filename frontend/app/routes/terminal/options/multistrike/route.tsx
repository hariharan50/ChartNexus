import { useQuery } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';
import EChart from '$shared/charts/EChart';
import {
  buildMultiSeriesOption,
  seriesColor,
  SERIES_PALETTE,
  type SeriesLine
} from '$shared/charts/options/multi-series';
import { useChartTheme } from '$shared/charts/theme/use-chart-theme';
import { lastTradingDayIST } from '$shared/formatting/ist-clock';
import { cx } from '$shared/ui/cx';
import Select from '$shared/ui/Select';
import IconChart from '$shared/ui/icons/IconChart';
import SeriesToggle from '$shared/ui/SeriesToggle';
import ExpiryPicker from '../components/ExpiryPicker';
import HistoryMode, { type Mode } from '../components/HistoryMode';
import StrikeLadder from './components/StrikeLadder';
import {
  bucketIndices,
  callLegs,
  CALL_COLOR,
  clockLabel,
  csvFilename,
  dateLabel,
  DEFAULT_TIMEFRAME,
  defaultLegs,
  fmtPremium,
  fmtPrice,
  freshnessLabel,
  futureSeries,
  getStraddle,
  legKey,
  legLabel,
  legSeries,
  legSeriesLabel,
  legsOnLadder,
  multistrikeCsv,
  OI_INSTRUMENTS,
  pick,
  putLegs,
  PUT_COLOR,
  REFETCH_MS,
  STALE_AFTER_MS,
  sumLegs,
  TIMEFRAMES,
  toggleLeg,
  VIEW_MODES,
  type Leg,
  type StraddleView,
  type Timeframe,
  type ViewMode
} from './multistrike-data';
import s from './route.module.css';
import type { Route } from './+types/route';

export const meta: Route.MetaFunction = () => [{ title: 'MultiStrike Chart · Options Lab' }];

/**
 * Blank margin right of the premium axis labels.
 *
 * Same reasoning as the Straddle chart: the shared 96px default budgets for
 * value pills hanging outside the plot, and these sit inside it.
 */
const CHART_RIGHT_GUTTER = 16;

/** The single Combined line — blue, the palette's second entry. */
const COMBINED_COLOR = SERIES_PALETTE[1];

export default function MultistrikeChart() {
  const [instIdx, setInstIdx] = useState(0);
  const [dataMode, setDataMode] = useState<Mode>('live');
  const [date, setDate] = useState(lastTradingDayIST);
  const [timeframe, setTimeframe] = useState<Timeframe>(DEFAULT_TIMEFRAME);
  const [view, setView] = useState<ViewMode>('individual');
  const [showFuture, setShowFuture] = useState(true);
  const [hidden, setHidden] = useState<Set<string>>(() => new Set());
  const [sidebarOpen, setSidebarOpen] = useState(true);
  // `undefined` means "whatever the backend picks" — the nearest expiry.
  const [expiry, setExpiry] = useState<string | undefined>(undefined);
  // Bumped by Reset zoom: it feeds `resetKey`, and a rebuild is what re-applies
  // the option's own window — the merge path deliberately leaves the reader's
  // zoom alone (see `use-echart.ts`).
  const [zoomNonce, setZoomNonce] = useState(0);
  /**
   * `null` until the reader picks, then their explicit selection.
   *
   * Distinguishing "hasn't chosen" from "chose nothing" is what lets the page
   * open on the ATM pair without that default fighting a reader who removed
   * every leg on purpose.
   */
  const [picked, setPicked] = useState<Leg[] | null>(null);

  const theme = useChartTheme();
  const instrument = OI_INSTRUMENTS[instIdx] ?? OI_INSTRUMENTS[0]!;

  function cycle(delta: number) {
    setInstIdx((current) => (current + delta + OI_INSTRUMENTS.length) % OI_INSTRUMENTS.length);
    // 23950 means nothing on BANKNIFTY, so a selection cannot survive the move.
    setPicked(null);
    setHidden(new Set());
  }

  const historyDate = dataMode === 'historical' ? date : undefined;
  const query = useQuery<StraddleView>({
    queryKey: ['options-lab', 'straddle-series', instrument.symbol, dataMode, historyDate, expiry],
    queryFn: () => getStraddle(instrument.symbol, { date: historyDate, expiry }),
    refetchInterval: dataMode === 'live' ? REFETCH_MS : false
  });

  const vw = query.data;

  /** What is actually plotted: the reader's picks, or the opening ATM pair. */
  const legs = useMemo(
    () => (picked === null ? defaultLegs(vw) : legsOnLadder(picked, vw)),
    [picked, vw]
  );

  function toggle(leg: Leg) {
    setPicked((current) => toggleLeg(current === null ? defaultLegs(vw) : current, leg));
  }

  function removeLeg(leg: Leg) {
    setPicked((current) => {
      const base = current === null ? defaultLegs(vw) : current;
      return base.filter((entry) => legKey(entry) !== legKey(leg));
    });
  }

  /** The lines the current mode draws, already bucketed to the timeframe. */
  const plot = useMemo(() => {
    if (!vw || vw.frames.length === 0) return null;

    const keep = bucketIndices(vw.t, timeframe);
    const timestamps = pick(vw.t, keep);
    const futures = pick(futureSeries(vw), keep);

    const lines: SeriesLine[] =
      view === 'individual'
        ? legs.map((leg, index) => ({
            id: legKey(leg),
            label: legSeriesLabel(leg),
            color: seriesColor(index),
            values: pick(legSeries(vw, leg), keep)
          }))
        : view === 'call_put'
          ? [
              {
                id: 'total-call',
                label: 'Total Call Premium',
                color: CALL_COLOR,
                values: pick(sumLegs(vw, callLegs(legs)), keep)
              },
              {
                id: 'total-put',
                label: 'Total Put Premium',
                color: PUT_COLOR,
                values: pick(sumLegs(vw, putLegs(legs)), keep)
              }
            ].filter((line) => line.values.some((value) => value !== null))
          : legs.length === 0
            ? []
            : [
                {
                  id: 'combined',
                  label: 'Combined Premium',
                  color: COMBINED_COLOR,
                  values: pick(sumLegs(vw, legs), keep)
                }
              ];

    return { timestamps, futures, lines };
  }, [vw, legs, timeframe, view]);

  /** The same lines minus the ones the reader has an eye closed on. */
  const visible = useMemo(
    () => (plot ? plot.lines.filter((line) => !hidden.has(line.id)) : []),
    [plot, hidden]
  );

  const option = useMemo(() => {
    if (!plot) return null;
    return buildMultiSeriesOption(
      {
        timestamps: plot.timestamps,
        futures: plot.futures,
        lines: visible,
        formatValue: fmtPremium,
        formatPrice: fmtPrice,
        valueAxisName: 'Premium',
        showFutures: showFuture,
        rightGutter: CHART_RIGHT_GUTTER,
        zoomable: true
      },
      theme
    );
  }, [plot, visible, showFuture, theme]);

  // -- live clock -----------------------------------------------------------
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(t);
  }, []);

  const updatedAt = query.dataUpdatedAt;
  const isStale = dataMode === 'live' && Boolean(updatedAt) && now - updatedAt > STALE_AFTER_MS;

  function download() {
    if (!plot) return;
    const csv = multistrikeCsv(
      plot.timestamps,
      plot.futures,
      plot.lines.map((line) => ({ label: line.label, values: line.values }))
    );
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = csvFilename(instrument.symbol, vw);
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className={s.page}>
      {query.isError ? (
        <div className={s.banner} role="alert">
          <span>Couldn’t load the MultiStrike chart.</span>
          <button type="button" onClick={() => void query.refetch()}>
            Retry
          </button>
        </div>
      ) : !vw && query.isPending ? (
        <div className={cx(s.panel, s.muted)}>Loading MultiStrike Chart…</div>
      ) : vw && vw.data_quality === 'empty' ? (
        // The mode toggle rides along so a picked date that turns up empty is
        // not a dead end — the reader can change the date or return to Live.
        <div className={cx(s.panel, s.emptyPanel)}>
          <HistoryMode mode={dataMode} date={date} onMode={setDataMode} onDate={setDate} />
          <p className={s.muted}>
            {dataMode === 'historical'
              ? 'No session archived for that date.'
              : 'No premiums recorded for today yet — the series fills in as the ingest worker captures the chain.'}
          </p>
        </div>
      ) : vw && plot ? (
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

                <div className={s.twoUp}>
                  <div>
                    <ExpiryPicker
                      instrument={instrument.symbol}
                      value={expiry}
                      onChange={setExpiry}
                      resolved={vw.expiry_date}
                      archiveBound
                      dataQuality={vw?.data_quality}
                    />
                  </div>
                  <div>
                    <p className={s.subLabel}>Timeframe</p>
                    <Select
                      className={s.selectNative}
                      value={timeframe}
                      ariaLabel="Timeframe"
                      onChange={setTimeframe}
                      options={TIMEFRAMES.map((entry) => ({
                        value: entry.value,
                        label: entry.label
                      }))}
                    />
                  </div>
                </div>

                <p className={s.subLabel}>Selected Strikes</p>
                {legs.length === 0 ? (
                  <p className={s.hint}>Nothing plotted — add a call or a put below.</p>
                ) : (
                  <div className={s.chips}>
                    {legs.map((leg, index) => (
                      <span key={legKey(leg)} className={s.chip}>
                        <span
                          className={s.chipDot}
                          style={{ background: seriesColor(index) }}
                          aria-hidden="true"
                        />
                        {legLabel(leg)}
                        <button
                          type="button"
                          className={s.chipX}
                          aria-label={`Remove ${legLabel(leg)}`}
                          onClick={() => removeLeg(leg)}
                        >
                          ×
                        </button>
                      </span>
                    ))}
                  </div>
                )}

                <p className={s.subLabel}>Add Strikes</p>
                <StrikeLadder
                  strikes={vw.strikes}
                  atm={vw.atm_strike}
                  selected={legs}
                  onToggle={toggle}
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
                    MultiStrike Chart
                  </h2>

                  <div className={s.viewToggle} role="tablist" aria-label="Series mode">
                    {VIEW_MODES.map((entry) => (
                      <button
                        key={entry.value}
                        type="button"
                        role="tab"
                        aria-selected={view === entry.value}
                        className={cx(s.seg, view === entry.value && s.active)}
                        onClick={() => setView(entry.value)}
                      >
                        {entry.label}
                      </button>
                    ))}
                  </div>

                  <div className={s.viewToggle} role="tablist" aria-label="Chart mode">
                    <button
                      type="button"
                      role="tab"
                      aria-selected={true}
                      className={cx(s.seg, s.active)}
                    >
                      Simple
                    </button>
                    <button
                      type="button"
                      role="tab"
                      aria-selected={false}
                      className={cx(s.seg, s.disabled)}
                      disabled
                      title="Drawing tools — coming soon"
                    >
                      Drawing
                    </button>
                  </div>
                </div>

                <div className={s.chartTopRight}>
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
                    className={s.zoomReset}
                    onClick={() => setZoomNonce((n) => n + 1)}
                    title="Back to the whole session"
                  >
                    ⤢ Reset zoom
                  </button>
                  <button
                    type="button"
                    className={s.download}
                    onClick={download}
                    title="Download the plotted series as CSV"
                  >
                    ↓ CSV
                  </button>
                </div>
              </div>

              <div className={s.legend}>
                <SeriesToggle
                  label="Future"
                  dashed
                  on={showFuture}
                  onToggle={() => setShowFuture((on) => !on)}
                />
                {plot.lines.map((line) => (
                  <SeriesToggle
                    key={line.id}
                    label={line.label}
                    color={line.color}
                    on={!hidden.has(line.id)}
                    onToggle={() =>
                      setHidden((current) => {
                        const next = new Set(current);
                        if (!next.delete(line.id)) next.add(line.id);
                        return next;
                      })
                    }
                  />
                ))}
              </div>

              {plot.lines.length === 0 ? (
                <p className={s.empty}>
                  Nothing selected — add a call or a put from the ladder to plot it.
                </p>
              ) : plot.timestamps.length === 0 || option === null ? (
                <p className={s.empty}>No captures recorded for this session yet.</p>
              ) : (
                <EChart
                  option={option}
                  resetKey={`${view}-${timeframe}-${instrument.symbol}-${zoomNonce}`}
                  className={s.chart}
                />
              )}

              <p className={s.caption}>
                {view === 'individual'
                  ? 'Each selected contract’s premium through the session, one line per leg.'
                  : view === 'call_put'
                    ? 'The selected calls and the selected puts, each summed into one premium — what the two sides of the basket cost together.'
                    : 'Every selected contract summed into a single premium — for one strike’s call and put, that is the straddle.'}{' '}
                Future is the tradable current-month future on the left axis. Scroll over the plot
                to zoom the clock, drag inside it to pan, or drag the time axis itself to stretch
                and squeeze the window.
              </p>
            </section>
          </div>
        </div>
      ) : null}
    </div>
  );
}
