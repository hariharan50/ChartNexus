import { useQuery } from '@tanstack/react-query';
import { type ReactNode, useEffect, useMemo, useState } from 'react';
import EChart from '$shared/charts/EChart';
import { buildMultiSeriesOption, type SeriesLine } from '$shared/charts/options/multi-series';
import { useChartTheme } from '$shared/charts/theme/use-chart-theme';
import { isoDateIST, lastTradingDayIST } from '$shared/formatting/ist-clock';
import { cx } from '$shared/ui/cx';
import IconChart from '$shared/ui/icons/IconChart';
import IconEye from '$shared/ui/icons/IconEye';
import IconEyeOff from '$shared/ui/icons/IconEyeOff';
import ExpiryPicker from '../components/ExpiryPicker';
import HistoryMode, { type Mode } from '../components/HistoryMode';
import StrikePicker from './components/StrikePicker';
import {
  atmOf,
  bucketIndices,
  CALL_COLOR,
  changeFromRef,
  clockLabel,
  csvFilename,
  dateLabel,
  DEFAULT_ATM_SPAN,
  DEFAULT_FIXED_SPAN,
  DEFAULT_TIMEFRAME,
  firstTotal,
  fmtPremium,
  fmtPrice,
  fmtSignedPremium,
  freshnessLabel,
  futureSeries,
  getStraddle,
  OI_INSTRUMENTS,
  pick,
  premiumDecayCsv,
  premiumTotals,
  prevCloseTotals,
  prevTradingDay,
  PUT_COLOR,
  rangeLabel,
  REFETCH_MS,
  resolveWindow,
  RUNNING_AVG_PERIOD,
  sma,
  STALE_AFTER_MS,
  TIMEFRAMES,
  windowIndices,
  type Baseline,
  type PremiumCsvRow,
  type Selection,
  type SelectionMode,
  type StraddleView,
  type Timeframe
} from './premium-decay-data';
import s from './route.module.css';
import type { Route } from './+types/route';

export const meta: Route.MetaFunction = () => [{ title: 'Premium Decay · Options Lab' }];

/**
 * The `echarts.connect` group the two stacked charts share.
 *
 * They plot the same session against the same clock, one above the other, so a
 * zoom or a crosshair on either has to be a zoom or a crosshair on both — a
 * window that reads 11:00–14:00 on top and the whole day underneath invites
 * exactly the comparison it cannot support.
 */
const CHART_GROUP = 'premium-decay';

const ATM_SPAN_MAX = 20;
const FIXED_SPAN_MAX = 20;

/**
 * Blank margin right of the price axis labels.
 *
 * Both charts here run the full width of the page, and the shared option's
 * 96px default — sized for value pills that hang *outside* the plot — left a
 * finger-wide empty column between the axis labels and the panel border. These
 * pills sit inside the plot (the axis keeps a 6% blank track past the newest
 * point, which is wider than a tag), so all this has to cover is the gap the
 * panel's own padding would want anyway.
 */
const CHART_RIGHT_GUTTER = 16;

export default function PremiumDecay() {
  const [instIdx, setInstIdx] = useState(0);
  const [dataMode, setDataMode] = useState<Mode>('live');
  const [date, setDate] = useState(lastTradingDayIST);
  const [timeframe, setTimeframe] = useState<Timeframe>(DEFAULT_TIMEFRAME);
  const [baseline, setBaseline] = useState<Baseline>('day_open');
  const [runningAvg, setRunningAvg] = useState(false);
  const [showFuture, setShowFuture] = useState(true);
  const [showCe, setShowCe] = useState(true);
  const [showPe, setShowPe] = useState(true);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  // `undefined` means "whatever the backend picks" — the nearest expiry.
  const [expiry, setExpiry] = useState<string | undefined>(undefined);
  // Bumped by Reset zoom: it feeds `resetKey`, and a rebuild is what re-applies
  // the option's own window — the merge path deliberately leaves the reader's
  // zoom alone (see `use-echart.ts`).
  const [zoomNonce, setZoomNonce] = useState(0);

  // Strike selection — the three mutually-exclusive windows.
  const [mode, setMode] = useState<SelectionMode>('atm');
  const [atmSpan, setAtmSpan] = useState(DEFAULT_ATM_SPAN);
  const [fixedStrike, setFixedStrike] = useState<number | null>(null);
  const [fixedSpan, setFixedSpan] = useState(DEFAULT_FIXED_SPAN);
  const [customPicks, setCustomPicks] = useState<number[]>([]);
  const [picker, setPicker] = useState<null | 'custom'>(null);

  const theme = useChartTheme();
  const instrument = OI_INSTRUMENTS[instIdx] ?? OI_INSTRUMENTS[0]!;

  function cycle(delta: number) {
    setInstIdx((current) => (current + delta + OI_INSTRUMENTS.length) % OI_INSTRUMENTS.length);
    // Strikes are instrument-specific, so no selection survives the switch.
    setMode('atm');
    setFixedStrike(null);
    setCustomPicks([]);
  }

  const historyDate = dataMode === 'historical' ? date : undefined;
  const query = useQuery<StraddleView>({
    queryKey: ['options-lab', 'straddle-series', instrument.symbol, dataMode, historyDate, expiry],
    queryFn: () => getStraddle(instrument.symbol, { date: historyDate, expiry }),
    refetchInterval: dataMode === 'live' ? REFETCH_MS : false
  });

  const vw = query.data;

  // The "1m Close" baseline reads against the previous session's close, which
  // this session's payload does not carry — so fetch the prior trading day too,
  // only while that mode is on. Its last capture is the prev-close reference.
  const sessionDate = dataMode === 'historical' ? date : isoDateIST(0);
  const prevDate = useMemo(() => prevTradingDay(sessionDate), [sessionDate]);
  const prevQuery = useQuery<StraddleView>({
    queryKey: ['options-lab', 'straddle-series', instrument.symbol, 'prev-close', prevDate],
    queryFn: () => getStraddle(instrument.symbol, { date: prevDate }),
    enabled: baseline === 'min_close'
  });
  const prevView = prevQuery.data;

  // Rebuilt only when a part actually changes, so it can be a memo dependency
  // rather than forcing every derivation to re-run on each render.
  const selection: Selection = useMemo(
    () => ({ mode, atmSpan, fixedStrike, fixedSpan, customPicks }),
    [mode, atmSpan, fixedStrike, fixedSpan, customPicks]
  );

  // The whole plot: window → totals → bucket → change → optional running average.
  const derived = useMemo(() => {
    if (!vw || vw.frames.length === 0) return null;
    const window = resolveWindow(vw, selection);
    const indices = windowIndices(vw.strikes, window.strikes);
    const totals = premiumTotals(vw, indices);
    const keep = bucketIndices(vw.t, timeframe);
    const times = pick(vw.t, keep);

    let ceTotal = pick(totals.ce, keep);
    let peTotal = pick(totals.pe, keep);

    // The reference each change is read against: today's open, or the prior
    // session's close for "1m Close" — falling back to the open per leg when the
    // prior day carried none of the window's strikes yet.
    const prevClose = baseline === 'min_close' ? prevCloseTotals(prevView, window.strikes) : null;
    const ceRef =
      baseline === 'min_close' && prevClose?.ce != null ? prevClose.ce : firstTotal(ceTotal);
    const peRef =
      baseline === 'min_close' && prevClose?.pe != null ? prevClose.pe : firstTotal(peTotal);
    const prevMissing =
      baseline === 'min_close' && (prevClose?.ce == null || prevClose?.pe == null);

    let ceChange = changeFromRef(ceTotal, ceRef);
    let peChange = changeFromRef(peTotal, peRef);
    if (runningAvg) {
      ceTotal = sma(ceTotal, RUNNING_AVG_PERIOD);
      peTotal = sma(peTotal, RUNNING_AVG_PERIOD);
      ceChange = sma(ceChange, RUNNING_AVG_PERIOD);
      peChange = sma(peChange, RUNNING_AVG_PERIOD);
    }

    return {
      window,
      times,
      futures: pick(futureSeries(vw), keep),
      ceTotal,
      peTotal,
      ceChange,
      peChange,
      prevMissing
    };
  }, [vw, prevView, selection, timeframe, baseline, runningAvg]);

  // The strike span each card advertises, computed for its own mode so the
  // labels stay populated even while another mode is the live one.
  const atmRange = useMemo(
    () => (vw ? resolveWindow(vw, { ...selection, mode: 'atm' }).range : null),
    [vw, selection]
  );
  const fixedRange = useMemo(
    () => (vw ? resolveWindow(vw, { ...selection, mode: 'fixed' }).range : null),
    [vw, selection]
  );

  const decayOption = useMemo(() => {
    if (!derived || derived.window.strikes.length === 0) return null;
    const lines: SeriesLine[] = [];
    if (showCe) {
      lines.push({
        id: 'ce',
        label: 'CE Change',
        color: CALL_COLOR,
        values: derived.ceChange,
        fill: true,
        fillOrigin: 0
      });
    }
    if (showPe) {
      lines.push({
        id: 'pe',
        label: 'PE Change',
        color: PUT_COLOR,
        values: derived.peChange,
        fill: true,
        fillOrigin: 0
      });
    }
    return buildMultiSeriesOption(
      {
        timestamps: derived.times,
        futures: derived.futures,
        lines,
        formatValue: fmtSignedPremium,
        formatPrice: fmtPrice,
        valueAxisName: 'Premium Δ',
        referenceLine: { value: 0, label: '0' },
        showFutures: showFuture,
        rightGutter: CHART_RIGHT_GUTTER,
        zoomable: true
      },
      theme
    );
  }, [derived, showFuture, showCe, showPe, theme]);

  const cvpOption = useMemo(() => {
    if (!derived || derived.window.strikes.length === 0) return null;
    const lines: SeriesLine[] = [];
    if (showCe) lines.push({ id: 'ce', label: 'CE', color: CALL_COLOR, values: derived.ceTotal });
    if (showPe) lines.push({ id: 'pe', label: 'PE', color: PUT_COLOR, values: derived.peTotal });
    return buildMultiSeriesOption(
      {
        timestamps: derived.times,
        futures: derived.futures,
        lines,
        formatValue: fmtPremium,
        formatPrice: fmtPrice,
        valueAxisName: 'Premium',
        showFutures: showFuture,
        rightGutter: CHART_RIGHT_GUTTER,
        zoomable: true
      },
      theme
    );
  }, [derived, showFuture, showCe, showPe, theme]);

  // -- live clock -----------------------------------------------------------
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(t);
  }, []);

  const updatedAt = query.dataUpdatedAt;
  const isStale = dataMode === 'live' && Boolean(updatedAt) && now - updatedAt > STALE_AFTER_MS;

  function download() {
    if (!derived) return;
    const rows: PremiumCsvRow[] = derived.times.map((t, i) => ({
      t,
      ce: derived.ceTotal[i] ?? null,
      pe: derived.peTotal[i] ?? null,
      future: derived.futures[i] ?? null
    }));
    const blob = new Blob([premiumDecayCsv(rows)], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = csvFilename(instrument.symbol, vw);
    link.click();
    URL.revokeObjectURL(url);
  }

  const strikeCount = derived?.window.strikes.length ?? 0;
  const atm = vw ? atmOf(vw) : null;

  return (
    <div className={s.page}>
      {query.isError ? (
        <div className={s.banner} role="alert">
          <span>Couldn’t load the premium decay charts.</span>
          <button type="button" onClick={() => void query.refetch()}>
            Retry
          </button>
        </div>
      ) : !vw && query.isPending ? (
        <div className={cx(s.panel, s.muted)}>Loading Premium Decay…</div>
      ) : vw && vw.data_quality === 'empty' ? (
        <div className={cx(s.panel, s.emptyPanel)}>
          <HistoryMode mode={dataMode} date={date} onMode={setDataMode} onDate={setDate} />
          <p className={s.muted}>
            {dataMode === 'historical'
              ? 'No session archived for that date.'
              : 'No premium data recorded for today yet — the charts fill in as the ingest worker captures the chain.'}
          </p>
        </div>
      ) : vw && derived ? (
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

                {/* ATM ± range */}
                <ModeCard
                  active={mode === 'atm'}
                  label="ATM ± range"
                  onSelect={() => setMode('atm')}
                >
                  <div className={s.modeHead}>
                    <span className={s.modeTitle}>ATM ± range</span>
                    <Stepper
                      value={atmSpan}
                      min={1}
                      max={ATM_SPAN_MAX}
                      onChange={(v) => {
                        setAtmSpan(v);
                        setMode('atm');
                      }}
                    />
                  </div>
                  <div className={s.rangeRow}>
                    <span className={s.rangeLabel}>Range</span>
                    <span className={s.rangeValue}>{rangeLabel(atmRange)}</span>
                  </div>
                </ModeCard>

                {/* Fixed Strike ± range */}
                <ModeCard
                  active={mode === 'fixed'}
                  label="Fixed Strike ± range"
                  onSelect={() => setMode('fixed')}
                >
                  <div className={s.modeHead}>
                    <span className={s.modeTitle}>Fixed Strike ± range</span>
                    <Stepper
                      value={fixedSpan}
                      min={1}
                      max={FIXED_SPAN_MAX}
                      onChange={(v) => {
                        setFixedSpan(v);
                        setMode('fixed');
                      }}
                    />
                  </div>
                  <div className={s.modeField}>
                    <span className={s.fieldLabel}>Center Strike</span>
                    <select
                      className={s.fieldSelect}
                      aria-label="Center strike"
                      value={String(fixedStrike ?? atm ?? vw.strikes[0] ?? '')}
                      onChange={(e) => {
                        setFixedStrike(Number(e.currentTarget.value));
                        setMode('fixed');
                      }}
                    >
                      {vw.strikes.map((st) => (
                        <option key={st} value={st}>
                          {st}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className={s.modeField}>
                    <span className={s.fieldLabel}>Range</span>
                    <span className={s.rangeValue}>{rangeLabel(fixedRange)}</span>
                  </div>
                </ModeCard>

                {/* Custom Strikes */}
                <ModeCard
                  active={mode === 'custom'}
                  label="Custom Strikes"
                  onSelect={() => (customPicks.length ? setMode('custom') : setPicker('custom'))}
                >
                  <div className={s.modeHead}>
                    <span className={s.modeTitle}>Custom Strikes</span>
                    <button
                      type="button"
                      className={s.selectBtn}
                      onClick={(e) => {
                        e.stopPropagation();
                        setPicker('custom');
                      }}
                    >
                      Select
                    </button>
                  </div>
                  {mode === 'custom' ? (
                    <p className={s.modeSummary}>
                      {customPicks.length === 0
                        ? 'No strikes chosen yet.'
                        : `${customPicks.length} strike${customPicks.length > 1 ? 's' : ''}: ${[...customPicks].sort((a, b) => a - b).join(', ')}`}
                    </p>
                  ) : null}
                </ModeCard>
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

          {/* RIGHT MAIN — two stacked charts */}
          <div className={s.main}>
            {/* Premium Decay (CE / PE change) */}
            <section className={s.panel}>
              <div className={s.chartTop}>
                <div className={s.chartTopLeft}>
                  <h2 className={s.pTitle}>
                    <span className={s.ico} aria-hidden="true">
                      <IconChart />
                    </span>{' '}
                    Premium Decay
                  </h2>

                  <div className={s.viewToggle} role="tablist" aria-label="Baseline">
                    <button
                      type="button"
                      role="tab"
                      aria-selected={baseline === 'min_close'}
                      className={cx(s.seg, baseline === 'min_close' && s.active)}
                      onClick={() => setBaseline('min_close')}
                    >
                      1m Close
                    </button>
                    <button
                      type="button"
                      role="tab"
                      aria-selected={baseline === 'day_open'}
                      className={cx(s.seg, baseline === 'day_open' && s.active)}
                      onClick={() => setBaseline('day_open')}
                    >
                      Day Open
                    </button>
                  </div>

                  <div className={s.legend}>
                    <LegendToggle
                      label="Future"
                      dashed
                      on={showFuture}
                      onToggle={() => setShowFuture((v) => !v)}
                    />
                    <LegendToggle
                      label="CE Change"
                      color={CALL_COLOR}
                      on={showCe}
                      onToggle={() => setShowCe((v) => !v)}
                    />
                    <LegendToggle
                      label="PE Change"
                      color={PUT_COLOR}
                      on={showPe}
                      onToggle={() => setShowPe((v) => !v)}
                    />
                  </div>
                </div>

                <div className={s.chartTopRight}>
                  <button
                    type="button"
                    className={s.zoomReset}
                    onClick={() => setZoomNonce((n) => n + 1)}
                    title="Back to the whole session — both charts"
                  >
                    ⤢ Reset zoom
                  </button>
                  <button
                    type="button"
                    className={cx(s.switch, runningAvg && s.on)}
                    role="switch"
                    aria-checked={runningAvg}
                    onClick={() => setRunningAvg((v) => !v)}
                  >
                    Running Avg
                    <span className={s.track} aria-hidden="true">
                      <span className={s.knob} />
                    </span>
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
                    title="Download both totals as CSV"
                  >
                    ↓ CSV
                  </button>
                </div>
              </div>

              {decayOption === null ? (
                <p className={s.empty}>
                  {strikeCount === 0
                    ? 'Choose at least one strike to aggregate.'
                    : 'No captures recorded for this session yet.'}
                </p>
              ) : (
                <EChart
                  option={decayOption}
                  resetKey={`${mode}-${timeframe}-${baseline}-${runningAvg}-${showFuture}-${strikeCount}-${zoomNonce}`}
                  group={CHART_GROUP}
                  className={s.chart}
                />
              )}

              <p className={s.caption}>
                {baseline === 'day_open'
                  ? 'Change in total call and put premium over the window since today’s opening premium — built up above zero, bled off below.'
                  : derived.prevMissing
                    ? 'No prior session archived for the previous-close reference — showing change since today’s open instead.'
                    : 'Change in total call and put premium over the window since the previous session’s close — the overnight gap plus today’s move.'}{' '}
                Future is the current-month future on the left axis. Scroll over either plot to zoom
                the clock, drag inside it to pan, or drag the time axis itself to stretch and
                squeeze the window — both charts move together.
              </p>
            </section>

            {/* Call vs Put Premium (absolute totals) */}
            <section className={s.panel}>
              <div className={s.chartTop}>
                <div className={s.chartTopLeft}>
                  <h2 className={s.pTitle}>
                    <span className={s.ico} aria-hidden="true">
                      <IconChart />
                    </span>{' '}
                    Call vs Put Premium
                  </h2>

                  <div className={s.legend}>
                    <LegendToggle
                      label="Future"
                      dashed
                      on={showFuture}
                      onToggle={() => setShowFuture((v) => !v)}
                    />
                    <LegendToggle
                      label="CE"
                      color={CALL_COLOR}
                      on={showCe}
                      onToggle={() => setShowCe((v) => !v)}
                    />
                    <LegendToggle
                      label="PE"
                      color={PUT_COLOR}
                      on={showPe}
                      onToggle={() => setShowPe((v) => !v)}
                    />
                  </div>
                </div>
              </div>

              {cvpOption === null ? (
                <p className={s.empty}>
                  {strikeCount === 0
                    ? 'Choose at least one strike to aggregate.'
                    : 'No captures recorded for this session yet.'}
                </p>
              ) : (
                <EChart
                  option={cvpOption}
                  resetKey={`${mode}-${timeframe}-${runningAvg}-${showFuture}-${strikeCount}-${zoomNonce}`}
                  group={CHART_GROUP}
                  className={s.chart}
                />
              )}

              <p className={s.caption}>
                Total call and put premium summed across the {strikeCount} selected strike
                {strikeCount === 1 ? '' : 's'} at each capture.
              </p>
            </section>
          </div>
        </div>
      ) : null}

      {picker === 'custom' && vw ? (
        <StrikePicker
          strikes={vw.strikes}
          atm={atm}
          selectMode="multi"
          selected={customPicks}
          title="Custom strikes"
          hint="Pick the strikes to total premium across."
          onApply={(picks) => {
            setCustomPicks(picks);
            setMode('custom');
            setPicker(null);
          }}
          onClose={() => setPicker(null)}
        />
      ) : null}
    </div>
  );
}

/**
 * A strike-mode card whose whole box selects the mode.
 *
 * `role="button"` with a keyboard handler makes the box itself the control, so a
 * click anywhere selects the mode — while the inner stepper, select and Select
 * button keep working (their clicks bubble up to select the mode too, which is
 * what we want). The keyboard handler only fires when the card itself holds
 * focus, so Space/Enter on an inner control still operates that control.
 */
function ModeCard({
  active,
  label,
  onSelect,
  children
}: {
  active: boolean;
  label: string;
  onSelect: () => void;
  children: ReactNode;
}) {
  return (
    <div
      className={cx(s.modeCard, active && s.active)}
      role="button"
      tabIndex={0}
      aria-pressed={active}
      aria-label={`${label} mode`}
      onClick={onSelect}
      onKeyDown={(e) => {
        if (e.target === e.currentTarget && (e.key === 'Enter' || e.key === ' ')) {
          e.preventDefault();
          onSelect();
        }
      }}
    >
      {children}
    </div>
  );
}

/** A legend chip that shows/hides its series, with an eye that follows the state. */
function LegendToggle({
  label,
  color,
  dashed,
  on,
  onToggle
}: {
  label: string;
  color?: string;
  dashed?: boolean;
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
      {dashed ? (
        <span className={s.dash} aria-hidden="true" />
      ) : (
        <span className={s.swatch} style={{ background: color }} />
      )}
      <span className={s.label}>{label}</span>
    </button>
  );
}

/** A compact −/value/+ number stepper for the ± range cards. */
function Stepper({
  value,
  min,
  max,
  disabled,
  onChange
}: {
  value: number;
  min: number;
  max: number;
  disabled?: boolean;
  onChange: (value: number) => void;
}) {
  return (
    <div className={s.stepper}>
      <button
        type="button"
        aria-label="Decrease"
        disabled={disabled || value <= min}
        onClick={() => onChange(value - 1)}
      >
        −
      </button>
      <span className={s.value}>{value}</span>
      <button
        type="button"
        aria-label="Increase"
        disabled={disabled || value >= max}
        onClick={() => onChange(value + 1)}
      >
        +
      </button>
    </div>
  );
}
