import { useQuery } from '@tanstack/react-query';
import { Fragment, useEffect, useMemo, useRef, useState } from 'react';
import EChart from '$shared/charts/EChart';
import { buildMultiSeriesOption, type SeriesLine } from '$shared/charts/options/multi-series';
import { useChartTheme } from '$shared/charts/theme/use-chart-theme';
import { lastTradingDayIST } from '$shared/formatting/ist-clock';
import { cx } from '$shared/ui/cx';
import IconChart from '$shared/ui/icons/IconChart';
import ExpiryPicker from '../components/ExpiryPicker';
import HistoryMode, { type Mode } from '../components/HistoryMode';
import {
  bollinger,
  bucketIndices,
  clockLabel,
  csvFilename,
  dateLabel,
  DEFAULT_TIMEFRAME,
  ema,
  fmtPrice,
  fmtStraddle,
  freshnessLabel,
  futureSeries,
  getStraddle,
  inferStep,
  OI_INSTRUMENTS,
  pick,
  REFETCH_MS,
  selectedSeries,
  sma,
  STALE_AFTER_MS,
  straddleCsv,
  strikeTable,
  TIMEFRAMES,
  type Selection,
  type StraddleCsvRow,
  type StraddleView,
  type Timeframe
} from './straddle-data';
import s from './route.module.css';
import type { Route } from './+types/route';

export const meta: Route.MetaFunction = () => [{ title: 'ATM Straddle Chart · Options Lab' }];

/**
 * Blank margin right of the straddle axis labels.
 *
 * The shared option's 96px default is sized for value pills that hang *outside*
 * the plot. This chart's pill sits inside it — the axis keeps a blank track past
 * the newest point, wider than the tag — so the default left a finger-wide empty
 * column between the axis labels and the panel border on a full-width chart.
 */
const CHART_RIGHT_GUTTER = 16;

const STRADDLE_COLOR = '#3b82f6';
const SMA_COLOR = '#f59e0b';
const EMA_COLOR = '#a855f7';
const BAND_COLOR = '#94a3b8';

/** Points either side of ATM shown in the sidebar table. */
const TABLE_SPAN_STEPS = 6;
const SMA_PERIOD = 20;
const EMA_PERIOD = 20;
const BB_PERIOD = 20;
const BB_K = 2;

interface Indicators {
  sma: boolean;
  ema: boolean;
  bollinger: boolean;
}

export default function AtmStraddleChart() {
  const [instIdx, setInstIdx] = useState(0);
  const [dataMode, setDataMode] = useState<Mode>('live');
  const [date, setDate] = useState(lastTradingDayIST);
  const [timeframe, setTimeframe] = useState<Timeframe>(DEFAULT_TIMEFRAME);
  const [selection, setSelection] = useState<Selection>('auto');
  const [drawing, setDrawing] = useState(false);
  const [showFuture, setShowFuture] = useState(true);
  const [areaFill, setAreaFill] = useState(true);
  const [indicators, setIndicators] = useState<Indicators>({
    sma: false,
    ema: false,
    bollinger: false
  });
  const [sidebarOpen, setSidebarOpen] = useState(true);
  // `undefined` means "whatever the backend picks" — the nearest expiry.
  const [expiry, setExpiry] = useState<string | undefined>(undefined);
  const [settingsOpen, setSettingsOpen] = useState(false);
  // Bumped by Reset zoom: it feeds `resetKey`, and a rebuild is what re-applies
  // the option's own window — the merge path deliberately leaves the reader's
  // zoom alone (see `use-echart.ts`).
  const [zoomNonce, setZoomNonce] = useState(0);

  const theme = useChartTheme();
  const instrument = OI_INSTRUMENTS[instIdx] ?? OI_INSTRUMENTS[0]!;

  function cycle(delta: number) {
    setInstIdx((current) => (current + delta + OI_INSTRUMENTS.length) % OI_INSTRUMENTS.length);
    // A strike that exists on NIFTY means nothing on BANKNIFTY, so an explicit
    // strike selection cannot survive an instrument change.
    setSelection('auto');
  }

  const historyDate = dataMode === 'historical' ? date : undefined;
  const query = useQuery<StraddleView>({
    queryKey: ['options-lab', 'straddle-series', instrument.symbol, dataMode, historyDate, expiry],
    queryFn: () => getStraddle(instrument.symbol, { date: historyDate, expiry }),
    refetchInterval: dataMode === 'live' ? REFETCH_MS : false
  });

  const vw = query.data;

  const table = useMemo(() => {
    if (!vw || vw.frames.length === 0) return [];
    return strikeTable(vw, inferStep(vw.strikes) * TABLE_SPAN_STEPS);
  }, [vw]);

  /** The plotted line set, bucketed to the timeframe. */
  const plot = useMemo(() => {
    if (!vw || vw.frames.length === 0) return null;

    const base = selectedSeries(vw, selection);
    const keep = bucketIndices(vw.t, timeframe);
    const values = pick(base.values, keep);

    const lines: SeriesLine[] = [
      { id: 'straddle', label: base.label, color: STRADDLE_COLOR, values, fill: areaFill }
    ];
    if (indicators.sma) {
      lines.push({
        id: 'sma',
        label: `SMA ${SMA_PERIOD}`,
        color: SMA_COLOR,
        values: sma(values, SMA_PERIOD)
      });
    }
    if (indicators.ema) {
      lines.push({
        id: 'ema',
        label: `EMA ${EMA_PERIOD}`,
        color: EMA_COLOR,
        values: ema(values, EMA_PERIOD)
      });
    }
    if (indicators.bollinger) {
      const bands = bollinger(values, BB_PERIOD, BB_K);
      lines.push(
        { id: 'bb-up', label: `BB Upper`, color: BAND_COLOR, values: bands.upper },
        { id: 'bb-lo', label: `BB Lower`, color: BAND_COLOR, values: bands.lower }
      );
    }

    return {
      label: base.label,
      timestamps: pick(vw.t, keep),
      futures: pick(futureSeries(vw), keep),
      values,
      lines
    };
  }, [vw, selection, timeframe, areaFill, indicators]);

  const option = useMemo(() => {
    if (!plot) return null;
    return buildMultiSeriesOption(
      {
        timestamps: plot.timestamps,
        futures: plot.futures,
        lines: plot.lines,
        formatValue: fmtStraddle,
        formatPrice: fmtPrice,
        valueAxisName: 'Straddle',
        showFutures: showFuture,
        rightGutter: CHART_RIGHT_GUTTER,
        zoomable: true
      },
      theme
    );
  }, [plot, showFuture, theme]);

  // -- live clock -----------------------------------------------------------
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(t);
  }, []);

  const updatedAt = query.dataUpdatedAt;
  const isStale = dataMode === 'live' && Boolean(updatedAt) && now - updatedAt > STALE_AFTER_MS;

  // Close the settings popover on an outside click.
  const settingsWrap = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!settingsOpen) return;
    const onDown = (e: PointerEvent) => {
      if (!settingsWrap.current?.contains(e.target as Node)) setSettingsOpen(false);
    };
    document.addEventListener('pointerdown', onDown);
    return () => document.removeEventListener('pointerdown', onDown);
  }, [settingsOpen]);

  function download() {
    if (!plot) return;
    const rows: StraddleCsvRow[] = plot.timestamps.map((t, i) => ({
      t,
      straddle: plot.values[i] ?? null,
      future: plot.futures[i] ?? null
    }));
    const blob = new Blob([straddleCsv(rows, plot.label)], { type: 'text/csv;charset=utf-8' });
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
          <span>Couldn’t load the straddle chart.</span>
          <button type="button" onClick={() => void query.refetch()}>
            Retry
          </button>
        </div>
      ) : !vw && query.isPending ? (
        <div className={cx(s.panel, s.muted)}>Loading Straddle Chart…</div>
      ) : vw && vw.data_quality === 'empty' ? (
        <div className={cx(s.panel, s.emptyPanel)}>
          <HistoryMode mode={dataMode} date={date} onMode={setDataMode} onDate={setDate} />
          <p className={s.muted}>
            {dataMode === 'historical'
              ? 'No session archived for that date.'
              : 'No straddle data recorded for today yet — the series fills in as the ingest worker captures the chain.'}
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
                    <select
                      className={s.selectNative}
                      aria-label="Timeframe"
                      value={timeframe}
                      onChange={(e) => setTimeframe(e.currentTarget.value as Timeframe)}
                    >
                      {TIMEFRAMES.map((tf) => (
                        <option key={tf.value} value={tf.value}>
                          {tf.label}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                <div className={s.tableWrap}>
                  <table className={s.strikeTable}>
                    <thead>
                      <tr>
                        <th aria-label="Select" />
                        <th>Strike</th>
                        <th>Call</th>
                        <th>Put</th>
                        <th>Straddle</th>
                      </tr>
                    </thead>
                    <tbody>
                      {table.map((row) => (
                        <Fragment key={row.strike}>
                          {row.atm ? (
                            <tr
                              className={s.autoRow}
                              onClick={() => setSelection('auto')}
                              aria-selected={selection === 'auto'}
                            >
                              <td>
                                <input
                                  type="radio"
                                  name="straddle-select"
                                  checked={selection === 'auto'}
                                  onChange={() => setSelection('auto')}
                                  aria-label="Auto rolling straddle"
                                />
                              </td>
                              <td colSpan={4} className={s.autoLabel}>
                                Auto Rolling Straddle
                              </td>
                            </tr>
                          ) : null}
                          <tr
                            className={cx(
                              row.atm && s.atmRow,
                              selection === row.strike && s.selRow
                            )}
                            onClick={() => setSelection(row.strike)}
                            aria-selected={selection === row.strike}
                          >
                            <td>
                              <input
                                type="radio"
                                name="straddle-select"
                                checked={selection === row.strike}
                                onChange={() => setSelection(row.strike)}
                                aria-label={`Straddle at ${row.strike}`}
                              />
                            </td>
                            <td className={s.mono}>{row.strike}</td>
                            <td className={cx(s.mono, s.call)}>{fmtCell(row.call)}</td>
                            <td className={cx(s.mono, s.put)}>{fmtCell(row.put)}</td>
                            <td className={s.mono}>{fmtCell(row.straddle)}</td>
                          </tr>
                        </Fragment>
                      ))}
                    </tbody>
                  </table>
                </div>
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
                    Straddle Chart
                  </h2>

                  <div className={s.viewToggle} role="tablist" aria-label="Chart mode">
                    <button
                      type="button"
                      role="tab"
                      aria-selected={!drawing}
                      className={cx(s.seg, !drawing && s.active)}
                      onClick={() => setDrawing(false)}
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

                  <div className={s.settings} ref={settingsWrap}>
                    <button
                      type="button"
                      className={s.settingsBtn}
                      aria-expanded={settingsOpen}
                      onClick={() => setSettingsOpen((v) => !v)}
                    >
                      ⚙ Add Indicator / Settings
                    </button>
                    {settingsOpen ? (
                      <div className={s.popover}>
                        <p className={s.popTitle}>Indicators</p>
                        <Check
                          label={`SMA ${SMA_PERIOD}`}
                          on={indicators.sma}
                          onToggle={() => setIndicators((i) => ({ ...i, sma: !i.sma }))}
                        />
                        <Check
                          label={`EMA ${EMA_PERIOD}`}
                          on={indicators.ema}
                          onToggle={() => setIndicators((i) => ({ ...i, ema: !i.ema }))}
                        />
                        <Check
                          label={`Bollinger ${BB_PERIOD}·${BB_K}`}
                          on={indicators.bollinger}
                          onToggle={() => setIndicators((i) => ({ ...i, bollinger: !i.bollinger }))}
                        />
                        <p className={s.popTitle}>Chart</p>
                        <Check
                          label="Show Future"
                          on={showFuture}
                          onToggle={() => setShowFuture((v) => !v)}
                        />
                        <Check
                          label="Area fill"
                          on={areaFill}
                          onToggle={() => setAreaFill((v) => !v)}
                        />
                      </div>
                    ) : null}
                  </div>

                  <div className={s.legend}>
                    <span className={cx(s.entry, s.readonly)}>
                      <span className={s.swatch} style={{ background: STRADDLE_COLOR }} />
                      {plot.label}
                    </span>
                    <button
                      type="button"
                      className={cx(s.entry, !showFuture && s.off)}
                      aria-pressed={showFuture}
                      onClick={() => setShowFuture((v) => !v)}
                    >
                      <span className={s.dash} aria-hidden="true" />
                      Future
                    </button>
                    {indicators.sma ? (
                      <LegendTag label={`SMA ${SMA_PERIOD}`} color={SMA_COLOR} />
                    ) : null}
                    {indicators.ema ? (
                      <LegendTag label={`EMA ${EMA_PERIOD}`} color={EMA_COLOR} />
                    ) : null}
                    {indicators.bollinger ? (
                      <LegendTag label={`Bollinger ${BB_PERIOD}·${BB_K}`} color={BAND_COLOR} />
                    ) : null}
                  </div>
                </div>

                <div className={s.chartTopRight}>
                  <button
                    type="button"
                    className={s.zoomReset}
                    onClick={() => setZoomNonce((n) => n + 1)}
                    title="Back to the whole session"
                  >
                    ⤢ Reset zoom
                  </button>
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
                    title="Download the plotted series as CSV"
                  >
                    ↓ CSV
                  </button>
                </div>
              </div>

              {plot.timestamps.length === 0 || option === null ? (
                <p className={s.empty}>No captures recorded for this session yet.</p>
              ) : (
                <EChart
                  option={option}
                  resetKey={`${selection}-${timeframe}-${showFuture}-${areaFill}-${indicators.sma}-${indicators.ema}-${indicators.bollinger}-${zoomNonce}`}
                  className={s.chart}
                />
              )}

              <p className={s.caption}>
                {selection === 'auto'
                  ? 'ATM Straddle is the call + put premium at each capture’s at-the-money strike — it rolls as the money moves through the day.'
                  : `Showing the ${selection} straddle (call + put premium) held fixed at that strike through the session.`}{' '}
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

/** A labelled checkbox row in the settings popover. */
function Check({ label, on, onToggle }: { label: string; on: boolean; onToggle: () => void }) {
  return (
    <label className={s.check}>
      <input type="checkbox" checked={on} onChange={onToggle} />
      <span>{label}</span>
    </label>
  );
}

/** A non-interactive legend swatch for an active indicator. */
function LegendTag({ label, color }: { label: string; color: string }) {
  return (
    <span className={cx(s.entry, s.readonly)}>
      <span className={s.swatch} style={{ background: color }} />
      {label}
    </span>
  );
}

/** A premium cell, or a dash where the leg was unquoted. */
function fmtCell(value: number | null): string {
  return value == null ? '—' : value.toFixed(2);
}
