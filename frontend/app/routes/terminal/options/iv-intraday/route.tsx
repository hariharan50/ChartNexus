import { useQuery } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';
import EChart from '$shared/charts/EChart';
import { buildMultiSeriesOption, seriesColor } from '$shared/charts/options/multi-series';
import { buildTermStructureOption } from '$shared/charts/options/term-structure';
import { useChartTheme } from '$shared/charts/theme/use-chart-theme';
import { getExpiries } from '$contexts/broker-connections/api';
import { lastTradingDayIST } from '$shared/formatting/ist-clock';
import { cx } from '$shared/ui/cx';
import IconChart from '$shared/ui/icons/IconChart';
import IconChevronDown from '$shared/ui/icons/IconChevronDown';
import IconEye from '$shared/ui/icons/IconEye';
import IconEyeOff from '$shared/ui/icons/IconEyeOff';
import HistoryMode, { type Mode } from '../components/HistoryMode';
import {
  atmIv,
  bucketIndices,
  clockLabel,
  csvFilename,
  dateLabel,
  DEFAULT_TIMEFRAME,
  defaultExpiries,
  expiryLabel,
  fmtIv,
  fmtPrice,
  freshnessLabel,
  futureSeries,
  getSkew,
  getTermStructure,
  intradayCsv,
  isFlatCurve,
  ivSeries,
  MAX_EXPIRIES,
  OI_INSTRUMENTS,
  pick,
  REFETCH_MS,
  shortExpiry,
  STALE_AFTER_MS,
  termCsv,
  TIMEFRAMES,
  toggleExpiry,
  VIEW_MODES,
  type SkewView,
  type TermStructureView,
  type Timeframe,
  type ViewMode
} from './iv-intraday-data';
import s from './route.module.css';
import type { Route } from './+types/route';

export const meta: Route.MetaFunction = () => [{ title: 'IV - Intraday · Options Lab' }];

/**
 * Blank margin right of the IV axis labels.
 *
 * Same reasoning as the Straddle chart: the shared 96px default budgets for a
 * value pill hanging outside the plot, and this one sits inside it.
 */
const CHART_RIGHT_GUTTER = 16;

/** The subject line. The same blue the sibling IV pages give implied volatility. */
const IV_COLOR = '#3b82f6';

export default function IvIntradayChart() {
  const [instIdx, setInstIdx] = useState(0);
  const [dataMode, setDataMode] = useState<Mode>('live');
  const [date, setDate] = useState(lastTradingDayIST);
  const [timeframe, setTimeframe] = useState<Timeframe>(DEFAULT_TIMEFRAME);
  const [view, setView] = useState<ViewMode>('intraday');
  const [showIv, setShowIv] = useState(true);
  const [showFuture, setShowFuture] = useState(true);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [zoomNonce, setZoomNonce] = useState(0);
  /** `null` until the reader picks — see the same pattern on MultiStrike. */
  const [picked, setPicked] = useState<string[] | null>(null);

  const theme = useChartTheme();
  const instrument = OI_INSTRUMENTS[instIdx] ?? OI_INSTRUMENTS[0]!;

  function cycle(delta: number) {
    setInstIdx((current) => (current + delta + OI_INSTRUMENTS.length) % OI_INSTRUMENTS.length);
    // Expiries are per instrument; a NIFTY date means nothing on SENSEX.
    setPicked(null);
  }

  const historyDate = dataMode === 'historical' ? date : undefined;

  // -- intraday -------------------------------------------------------------
  const skew = useQuery<SkewView>({
    queryKey: ['options-lab', 'skew', instrument.symbol, dataMode, historyDate],
    queryFn: () => getSkew(instrument.symbol, { date: historyDate }),
    refetchInterval: dataMode === 'live' ? REFETCH_MS : false,
    enabled: view === 'intraday'
  });

  const vw = skew.data;

  /** The plotted line set, bucketed to the timeframe. */
  const plot = useMemo(() => {
    if (!vw || vw.frames.length === 0) return null;
    const keep = bucketIndices(vw.t, timeframe);
    return {
      timestamps: pick(vw.t, keep),
      futures: pick(futureSeries(vw), keep),
      iv: pick(ivSeries(vw), keep)
    };
  }, [vw, timeframe]);

  const intradayOption = useMemo(() => {
    if (!plot) return null;
    return buildMultiSeriesOption(
      {
        timestamps: plot.timestamps,
        futures: plot.futures,
        lines: showIv
          ? [{ id: 'iv', label: 'IV', color: IV_COLOR, values: plot.iv }]
          : [],
        formatValue: fmtIv,
        formatPrice: fmtPrice,
        valueAxisName: 'IV',
        showFutures: showFuture,
        rightGutter: CHART_RIGHT_GUTTER,
        zoomable: true
      },
      theme
    );
  }, [plot, showIv, showFuture, theme]);

  // -- term structure -------------------------------------------------------
  const expiryQuery = useQuery({
    queryKey: ['market', 'expiries', instrument.symbol],
    queryFn: () => getExpiries(instrument.symbol),
    staleTime: 60 * 60_000
  });

  const listed = useMemo(() => expiryQuery.data?.expiries ?? [], [expiryQuery.data]);
  const expiries = useMemo(
    () => (picked === null ? defaultExpiries(listed) : picked),
    [picked, listed]
  );

  const term = useQuery<TermStructureView>({
    queryKey: ['options-lab', 'term-structure', instrument.symbol, expiries.join(',')],
    queryFn: () => getTermStructure(instrument.symbol, expiries),
    refetchInterval: REFETCH_MS,
    enabled: view === 'term' && expiries.length > 0
  });

  const points = useMemo(() => term.data?.points ?? [], [term.data]);

  const termOption = useMemo(
    () =>
      buildTermStructureOption(
        {
          points: points.map((point) => ({
            expiry: point.expiry,
            atmIv: point.atm_iv,
            daysToExpiry: point.days_to_expiry
          })),
          color: IV_COLOR,
          formatIv: fmtIv,
          formatExpiry: shortExpiry
        },
        theme
      ),
    [points, theme]
  );

  // -- live clock -----------------------------------------------------------
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const active = view === 'intraday' ? skew : term;
  const updatedAt = active.dataUpdatedAt;
  const isStale = dataMode === 'live' && Boolean(updatedAt) && now - updatedAt > STALE_AFTER_MS;
  const full = expiries.length >= MAX_EXPIRIES;

  function download() {
    const csv =
      view === 'term'
        ? termCsv(points)
        : plot
          ? intradayCsv(plot.timestamps, plot.iv, plot.futures)
          : '';
    if (!csv) return;
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = csvFilename(instrument.symbol, view, vw?.now_ts ?? term.data?.as_of);
    link.click();
    URL.revokeObjectURL(url);
  }

  const intradayEmpty = view === 'intraday' && vw && vw.data_quality === 'empty';

  return (
    <div className={s.page}>
      {active.isError ? (
        <div className={s.banner} role="alert">
          <span>Couldn’t load the implied volatility.</span>
          <button type="button" onClick={() => void active.refetch()}>
            Retry
          </button>
        </div>
      ) : !active.data && active.isPending ? (
        <div className={cx(s.panel, s.muted)}>Loading Implied Volatility Chart…</div>
      ) : intradayEmpty ? (
        <div className={cx(s.panel, s.emptyPanel)}>
          <HistoryMode mode={dataMode} date={date} onMode={setDataMode} onDate={setDate} />
          <p className={s.muted}>
            {dataMode === 'historical'
              ? 'No session archived for that date.'
              : 'No chain captures recorded for today yet — the volatility fills in as the ingest worker captures the chain.'}
          </p>
        </div>
      ) : (
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

                {view === 'intraday' ? (
                  <HistoryMode mode={dataMode} date={date} onMode={setDataMode} onDate={setDate} />
                ) : null}

                {view === 'intraday' ? (
                  <>
                    <p className={s.subLabel}>Expiry</p>
                    {/* Read-only here: the archive holds the nearest expiry
                        only, so a picker would promise history never captured. */}
                    <div className={s.select} title="The archived session's expiry">
                      <span>{expiryLabel(vw?.expiry_date ?? null)}</span>
                      <span className={s.caret} aria-hidden="true">
                        <IconChevronDown />
                      </span>
                    </div>

                    <p className={s.subLabel}>Timeframe</p>
                    <select
                      className={s.selectNative}
                      value={timeframe}
                      aria-label="Timeframe"
                      onChange={(e) => setTimeframe(e.currentTarget.value as Timeframe)}
                    >
                      {TIMEFRAMES.map((entry) => (
                        <option key={entry.value} value={entry.value}>
                          {entry.label}
                        </option>
                      ))}
                    </select>
                  </>
                ) : (
                  <>
                    <p className={s.subLabel}>Expiry (max {MAX_EXPIRIES})</p>
                    {expiries.length === 0 ? (
                      <p className={s.hint}>Pick an expiry below to draw the curve.</p>
                    ) : (
                      <div className={s.chips}>
                        {expiries.map((iso, index) => (
                          <span key={iso} className={s.chip}>
                            <span
                              className={s.chipDot}
                              style={{ background: seriesColor(index) }}
                              aria-hidden="true"
                            />
                            {shortExpiry(iso)}
                            <button
                              type="button"
                              className={s.chipX}
                              aria-label={`Remove ${shortExpiry(iso)}`}
                              onClick={() => setPicked(toggleExpiry(expiries, iso))}
                            >
                              ×
                            </button>
                          </span>
                        ))}
                      </div>
                    )}

                    <div className={s.expiryList}>
                      {listed.map((iso) => {
                        const on = expiries.includes(iso);
                        return (
                          <button
                            key={iso}
                            type="button"
                            className={cx(s.expiryRow, on && s.on)}
                            aria-pressed={on}
                            disabled={!on && full}
                            onClick={() => setPicked(toggleExpiry(expiries, iso))}
                          >
                            {expiryLabel(iso)}
                          </button>
                        );
                      })}
                    </div>
                    <p className={s.count} aria-live="polite">
                      {expiries.length} of {MAX_EXPIRIES} selected
                      {full ? ' — remove one to add another' : ''}
                    </p>
                  </>
                )}

                <p className={s.subLabel}>View</p>
                <div className={s.segRow} role="tablist" aria-label="View">
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
                    Implied Volatility Chart
                  </h2>

                  {view === 'intraday' ? (
                    <div className={s.legend}>
                      <Toggle
                        label="IV"
                        color={IV_COLOR}
                        on={showIv}
                        onToggle={() => setShowIv((v) => !v)}
                      />
                      <Toggle
                        label="Future"
                        dotted
                        on={showFuture}
                        onToggle={() => setShowFuture((v) => !v)}
                      />
                    </div>
                  ) : null}
                </div>

                <div className={s.chartTopRight}>
                  <span className={cx(s.live, isStale && s.stale)}>
                    <span className={cx(s.dot, active.isFetching && s.pulse)} />
                    <span>
                      {view === 'intraday' && dataMode === 'historical' ? (
                        <>Archived · {date}</>
                      ) : (
                        <>
                          {dateLabel(now)}, {clockLabel(now)} IST
                        </>
                      )}
                    </span>
                    <span className={s.sep} aria-hidden="true">
                      ·
                    </span>
                    <span>updated {freshnessLabel(updatedAt, now)}</span>
                  </span>
                  {view === 'intraday' ? (
                    <button
                      type="button"
                      className={s.zoomReset}
                      onClick={() => setZoomNonce((n) => n + 1)}
                      title="Back to the whole session"
                    >
                      ⤢ Reset zoom
                    </button>
                  ) : null}
                  <button
                    type="button"
                    className={s.download}
                    onClick={download}
                    title="Download the drawn series as CSV"
                  >
                    ↓ CSV
                  </button>
                </div>
              </div>

              {view === 'intraday' ? (
                plot === null || intradayOption === null ? (
                  <p className={s.empty}>No captures recorded for this session yet.</p>
                ) : (
                  <EChart
                    option={intradayOption}
                    resetKey={`${instrument.symbol}-${timeframe}-${dataMode}-${historyDate ?? ''}-${zoomNonce}`}
                    className={s.chart}
                  />
                )
              ) : points.length === 0 ? (
                <p className={s.empty}>
                  {expiries.length === 0
                    ? 'No expiry selected.'
                    : 'No volatility quoted for the selected expiries.'}
                </p>
              ) : (
                <EChart
                  option={termOption}
                  resetKey={`${instrument.symbol}-term-${expiries.join(',')}`}
                  className={s.chart}
                />
              )}

              <p className={s.caption}>
                {view === 'intraday' ? (
                  <>
                    At-the-money implied volatility at every capture, against the tradable future
                    on the left axis. The archive holds one expiry per session — the nearest — so
                    this is that contract’s volatility. Scroll over the plot to zoom the clock,
                    drag inside it to pan, or drag the time axis itself to stretch the window.
                  </>
                ) : (
                  <>
                    At-the-money volatility across expiries, priced live. There is no history
                    here and there cannot be: a term structure is several expiries quoted at one
                    instant, and each archived session holds only the nearest.
                    {isFlatCurve(points)
                      ? ' Every expiry is showing the same volatility, which means the data source is not varying its chain by expiry — expect this against mock data, not a live broker.'
                      : ''}
                  </>
                )}
              </p>
            </section>
          </div>
        </div>
      )}
    </div>
  );
}

/** A legend chip that shows/hides its series, with an eye that follows the state. */
function Toggle({
  label,
  color,
  dotted,
  on,
  onToggle
}: {
  label: string;
  color?: string;
  dotted?: boolean;
  on: boolean;
  onToggle: () => void;
}) {
  return (
    <button type="button" className={cx(s.entry, !on && s.off)} aria-pressed={on} onClick={onToggle}>
      <span className={s.eye} aria-hidden="true">
        {on ? <IconEye /> : <IconEyeOff />}
      </span>
      {dotted ? (
        <span className={s.dash} aria-hidden="true" />
      ) : (
        <span className={s.swatch} style={{ background: color }} />
      )}
      <span className={s.label}>{label}</span>
    </button>
  );
}
