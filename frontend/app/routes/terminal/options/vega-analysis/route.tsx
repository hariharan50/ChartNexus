import { useQuery } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';
import EChart from '$shared/charts/EChart';
import { buildVegaAnalysisOption, type VegaLine } from '$shared/charts/options/vega-analysis';
import { useChartTheme } from '$shared/charts/theme/use-chart-theme';
import { lastTradingDayIST } from '$shared/formatting/ist-clock';
import { cx } from '$shared/ui/cx';
import Select from '$shared/ui/Select';
import IconChart from '$shared/ui/icons/IconChart';
import IconEye from '$shared/ui/icons/IconEye';
import IconEyeOff from '$shared/ui/icons/IconEyeOff';
import ExpiryPicker from '../components/ExpiryPicker';
import HistoryMode, { type Mode } from '../components/HistoryMode';
import {
  bucketIndices,
  clockLabel,
  csvFilename,
  dateLabel,
  DEFAULT_TIMEFRAME,
  fmtPrice,
  fmtVega,
  frameTotals,
  freshnessLabel,
  getVega,
  inferStep,
  OI_INSTRUMENTS,
  pick,
  REFETCH_MS,
  STALE_AFTER_MS,
  STRIKE_SPAN,
  timeLabel,
  TIMEFRAMES,
  vegaCsv,
  withinWindow,
  CALL_COLOR,
  PUT_COLOR,
  type StrikeMode,
  type Timeframe,
  type VegaRow,
  type VegaView
} from './vega-data';
import s from './route.module.css';
import type { Route } from './+types/route';

export const meta: Route.MetaFunction = () => [{ title: 'Vega Analysis · Options Lab' }];

/** Purple for the Put-minus-Call spread, matching the reference. */
const DIFF_COLOR = '#a855f7';

const STRIKE_MODES: readonly { value: StrikeMode; label: string }[] = [
  { value: 'auto', label: 'Auto' },
  { value: 'fixed', label: 'Fixed' }
];

const VIEWS = [
  { value: 'chart', label: 'Chart' },
  { value: 'table', label: 'Chart + Table' }
] as const;
type View = (typeof VIEWS)[number]['value'];

export default function VegaAnalysis() {
  const [instIdx, setInstIdx] = useState(0);
  const [dataMode, setDataMode] = useState<Mode>('live');
  const [date, setDate] = useState(lastTradingDayIST);
  const [timeframe, setTimeframe] = useState<Timeframe>(DEFAULT_TIMEFRAME);
  const [strikeMode, setStrikeMode] = useState<StrikeMode>('auto');
  const [view, setView] = useState<View>('chart');
  const [showSynth, setShowSynth] = useState(true);
  const [showCall, setShowCall] = useState(true);
  const [showPut, setShowPut] = useState(true);
  const [showDiff, setShowDiff] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  // `undefined` means "whatever the backend picks" — the nearest expiry.
  const [expiry, setExpiry] = useState<string | undefined>(undefined);

  const theme = useChartTheme();
  const instrument = OI_INSTRUMENTS[instIdx] ?? OI_INSTRUMENTS[0]!;

  function cycle(delta: number) {
    setInstIdx((current) => (current + delta + OI_INSTRUMENTS.length) % OI_INSTRUMENTS.length);
  }

  const historyDate = dataMode === 'historical' ? date : undefined;
  const query = useQuery<VegaView>({
    queryKey: ['options-lab', 'vega', instrument.symbol, dataMode, historyDate, expiry],
    queryFn: () => getVega(instrument.symbol, { date: historyDate, expiry }),
    refetchInterval: dataMode === 'live' ? REFETCH_MS : false
  });

  const vw = query.data;

  /**
   * The Δ-since-open series, in the chosen strike window and timeframe.
   *
   * The window is summed per frame, then each side is measured against its own
   * first-frame total — so the two lines both start at zero and it is the *move*
   * away from the open that the chart shows. Auto re-centres the window on the
   * latest ATM (the day's current money); Fixed pins it to where the session
   * opened, so a drift in spot slides the money out of a static window on purpose.
   */
  const series = useMemo(() => {
    if (!vw || vw.frames.length === 0) return null;

    const frames = vw.frames;
    const step = inferStep(vw.strikes);
    const latest = frames[frames.length - 1]!;
    const opening = frames[0]!;
    const anchorFrame = strikeMode === 'auto' ? latest : opening;
    const anchor = anchorFrame.atm ?? anchorFrame.spot;
    const window = new Set(withinWindow(vw.strikes, anchor, step, STRIKE_SPAN));

    const callTot = frames.map((frame) => frameTotals(vw.strikes, frame, window).call);
    const putTot = frames.map((frame) => frameTotals(vw.strikes, frame, window).put);
    const baseCall = callTot[0] ?? 0;
    const basePut = putTot[0] ?? 0;

    const callDelta = callTot.map((value) => round2(value - baseCall));
    const putDelta = putTot.map((value) => round2(value - basePut));
    const diffDelta = putDelta.map((value, i) => round2(value - (callDelta[i] ?? 0)));
    const synth = frames.map((frame) => frame.synth_future);

    const keep = bucketIndices(vw.t, timeframe);
    return {
      timestamps: pick(vw.t, keep),
      synth: pick(synth, keep),
      call: pick(callDelta, keep),
      put: pick(putDelta, keep),
      diff: pick(diffDelta, keep),
      windowSize: window.size
    };
  }, [vw, strikeMode, timeframe]);

  const option = useMemo(() => {
    if (!series) return null;
    const lines: VegaLine[] = [];
    if (showCall)
      lines.push({
        id: 'call',
        label: 'Call Vega',
        color: CALL_COLOR,
        values: series.call,
        fill: true
      });
    if (showPut)
      lines.push({
        id: 'put',
        label: 'Put Vega',
        color: PUT_COLOR,
        values: series.put,
        fill: true
      });
    if (showDiff)
      lines.push({
        id: 'diff',
        label: 'Put-Call Difference',
        color: DIFF_COLOR,
        values: series.diff
      });

    return buildVegaAnalysisOption(
      {
        timestamps: series.timestamps,
        synth: series.synth,
        showSynth,
        lines,
        formatValue: fmtVega,
        formatPrice: fmtPrice,
        valueAxisName: 'Vega Δ (Cr)'
      },
      theme
    );
  }, [series, showSynth, showCall, showPut, showDiff, theme]);

  const rows = useMemo<VegaRow[]>(() => {
    if (!series) return [];
    return series.timestamps.map((t, i) => ({
      t,
      synth: series.synth[i] ?? null,
      call: series.call[i] ?? 0,
      put: series.put[i] ?? 0,
      diff: series.diff[i] ?? 0
    }));
  }, [series]);

  // -- live clock -----------------------------------------------------------
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(t);
  }, []);

  const updatedAt = query.dataUpdatedAt;
  const isStale = dataMode === 'live' && Boolean(updatedAt) && now - updatedAt > STALE_AFTER_MS;

  function download() {
    if (rows.length === 0) return;
    const blob = new Blob([vegaCsv(rows)], { type: 'text/csv;charset=utf-8' });
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
          <span>Couldn’t load vega analysis.</span>
          <button type="button" onClick={() => void query.refetch()}>
            Retry
          </button>
        </div>
      ) : !vw && query.isPending ? (
        <div className={cx(s.panel, s.muted)}>Loading Vega Analysis…</div>
      ) : vw && vw.data_quality === 'empty' ? (
        <div className={cx(s.panel, s.emptyPanel)}>
          <HistoryMode mode={dataMode} date={date} onMode={setDataMode} onDate={setDate} />
          <p className={s.muted}>
            {dataMode === 'historical'
              ? 'No session archived for that date.'
              : 'No vega data recorded for today yet — the series fills in as the ingest worker captures the chain.'}
          </p>
        </div>
      ) : vw && series ? (
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
                      ariaLabel="Timeframe"
                      value={timeframe}
                      onChange={setTimeframe}
                      options={TIMEFRAMES.map((tf) => ({ value: tf.value, label: tf.label }))}
                    />
                  </div>
                </div>

                <p className={s.subLabel}>View</p>
                <div className={s.modeGrid}>
                  {VIEWS.map((entry) => (
                    <button
                      key={entry.value}
                      type="button"
                      className={cx(s.seg, view === entry.value && s.active)}
                      aria-pressed={view === entry.value}
                      onClick={() => setView(entry.value)}
                    >
                      {entry.label}
                    </button>
                  ))}
                </div>

                <p className={s.subLabel}>Strike</p>
                <div className={s.filterRow}>
                  {STRIKE_MODES.map((entry) => (
                    <button
                      key={entry.value}
                      type="button"
                      className={cx(s.chip, strikeMode === entry.value && s.active)}
                      aria-pressed={strikeMode === entry.value}
                      onClick={() => setStrikeMode(entry.value)}
                    >
                      {entry.label}
                    </button>
                  ))}
                </div>
                <p className={s.hint}>
                  {strikeMode === 'auto'
                    ? 'Strikes re-centre on the latest-minute ATM.'
                    : 'Strikes stay pinned to the session-open ATM.'}
                </p>
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
                <h2 className={s.pTitle}>
                  <span className={s.ico} aria-hidden="true">
                    <IconChart />
                  </span>{' '}
                  Vega Analysis
                </h2>

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
                    className={s.download}
                    onClick={download}
                    title="Download the plotted series as CSV"
                  >
                    ↓ CSV
                  </button>
                </div>
              </div>

              <div className={s.legend}>
                <LegendEntry
                  label="Synth Future"
                  color={theme.axis}
                  on={showSynth}
                  onToggle={() => setShowSynth((v) => !v)}
                />
                <LegendEntry
                  label="Call Vega"
                  color={CALL_COLOR}
                  on={showCall}
                  onToggle={() => setShowCall((v) => !v)}
                />
                <LegendEntry
                  label="Put Vega"
                  color={PUT_COLOR}
                  on={showPut}
                  onToggle={() => setShowPut((v) => !v)}
                />
                <LegendEntry
                  label="Put-Call Difference"
                  color={DIFF_COLOR}
                  on={showDiff}
                  onToggle={() => setShowDiff((v) => !v)}
                />
              </div>

              {series.timestamps.length === 0 || option === null ? (
                <p className={s.empty}>No captures recorded for this session yet.</p>
              ) : (
                <EChart
                  option={option}
                  resetKey={`${showSynth}-${showCall}-${showPut}-${showDiff}-${timeframe}-${strikeMode}`}
                  className={s.chart}
                />
              )}

              {view === 'table' && rows.length > 0 ? (
                <div className={s.tableWrap}>
                  <table className={s.table}>
                    <thead>
                      <tr>
                        <th>Time</th>
                        <th>Synth Future</th>
                        <th>Call Vega Δ</th>
                        <th>Put Vega Δ</th>
                        <th>Put − Call</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((row) => (
                        <tr key={row.t}>
                          <td>{timeLabel(row.t)}</td>
                          <td>{row.synth == null ? '—' : fmtPrice(row.synth)}</td>
                          <td className={signClass(row.call)}>{fmtVega(row.call)}</td>
                          <td className={signClass(row.put)}>{fmtVega(row.put)}</td>
                          <td className={signClass(row.diff)}>{fmtVega(row.diff)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : null}

              <p className={s.caption}>
                Call and Put Vega are each side’s aggregate option vega across the{' '}
                {series.windowSize}-strike window around the money, in crore per one volatility
                point, shown as the change since the session open. Put-Call Difference is Put minus
                Call. Synth Future is the put-call-parity forward at the money.
                {vw.iv_coverage < 1
                  ? ` The broker quoted no volatility on ${Math.round((1 - vw.iv_coverage) * 100)}% of legs, which contribute nothing to these figures.`
                  : ''}
              </p>
            </section>
          </div>
        </div>
      ) : null}
    </div>
  );
}

/** A legend chip that shows and hides one series, styled like the OI legend. */
function LegendEntry({
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
      <span className={s.swatch} style={{ background: color }} aria-hidden="true" />
      {label}
    </button>
  );
}

function signClass(value: number): string | undefined {
  if (value > 0) return s.pos;
  if (value < 0) return s.neg;
  return undefined;
}

/** Two decimals is finer than any vega delta drives a decision on. */
function round2(value: number): number {
  return Math.round(value * 100) / 100;
}
