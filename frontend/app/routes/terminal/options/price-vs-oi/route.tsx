import { useQuery } from '@tanstack/react-query';
import { type ReactNode, useEffect, useMemo, useState } from 'react';
import EChart from '$shared/charts/EChart';
import type { EChartsCoreOption } from '$shared/charts/echarts-modules';
import { buildCallPutOption } from '$shared/charts/options/call-put';
import { buildPriceVsOiOption } from '$shared/charts/options/price-vs-oi';
import { useChartTheme } from '$shared/charts/theme/use-chart-theme';
import { lastTradingDayIST } from '$shared/formatting/ist-clock';
import { cx } from '$shared/ui/cx';
import IconChart from '$shared/ui/icons/IconChart';
import IconCheck from '$shared/ui/icons/IconCheck';
import IconChevronDown from '$shared/ui/icons/IconChevronDown';
import IconEye from '$shared/ui/icons/IconEye';
import IconEyeOff from '$shared/ui/icons/IconEyeOff';
import HistoryMode, { type Mode } from '../components/HistoryMode';
import {
  bucketIndices,
  CALL_COLOR,
  clockLabel,
  dateLabel,
  DEFAULT_TIMEFRAME,
  expiryLabel,
  fmtOi,
  fmtPcr,
  fmtPrice,
  freshnessLabel,
  getStrikeSeries,
  normalizeFromOpen,
  OI_INSTRUMENTS,
  pick,
  PUT_COLOR,
  REFETCH_MS,
  STALE_AFTER_MS,
  TIMEFRAMES,
  type StrikeSeriesView,
  type Timeframe
} from './price-vs-oi-data';
import s from './route.module.css';
import type { Route } from './+types/route';

export const meta: Route.MetaFunction = () => [{ title: 'Price vs OI · Options Lab' }];

const STRADDLE_COLOR = '#3b82f6';

/**
 * The `echarts.connect` group. All six panels share it, so ECharts drives one
 * crosshair, one synced tooltip and one zoom window across them — hovering or
 * zooming any panel moves all of them to the same instant/range.
 */
const CHART_GROUP = 'price-vs-oi';

/** The visible time window: the whole session, or its last N trading minutes. */
type RangeChoice = number | 'all';

const RANGES: readonly { value: RangeChoice; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 120, label: '2h' },
  { value: 60, label: '1h' },
  { value: 30, label: '30m' },
  { value: 15, label: '15m' }
];

/**
 * Per-panel series visibility, keyed `p<panel>.<series>`.
 *
 * Each panel owns its own toggles, so hiding CE on the Price chart leaves CE on
 * the OI and CE-Price-vs-OI charts alone. PCR overlays start off (the reference
 * greys them); everything else starts on.
 */
const DEFAULT_VIS: Record<string, boolean> = {
  'p1.ce': true,
  'p1.pe': true,
  'p1.pcr': false,
  'p2.straddle': true,
  'p2.pcr': true,
  'p3.ce': true,
  'p3.pe': true,
  'p3.pcr': false,
  'p4.ce': true,
  'p4.pe': true,
  'p5.price': true,
  'p5.oi': true,
  'p6.price': true,
  'p6.oi': true
};

export default function PriceVsOi() {
  const [instIdx, setInstIdx] = useState(0);
  const [dataMode, setDataMode] = useState<Mode>('live');
  const [date, setDate] = useState(lastTradingDayIST);
  const [timeframe, setTimeframe] = useState<Timeframe>(DEFAULT_TIMEFRAME);
  const [selectedStrike, setSelectedStrike] = useState<number | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  // Bumped to rebuild every panel at the full time range — the zoom reset. The
  // dataZoom window lives inside ECharts, so a fresh option is how it is cleared.
  const [zoomNonce, setZoomNonce] = useState(0);
  // The visible time window: the whole session, or its last N trading minutes.
  const [rangeMinutes, setRangeMinutes] = useState<RangeChoice>('all');

  // Per-panel series visibility — each panel's legend controls only its own
  // lines, so hiding CE on one chart never touches CE on the others.
  const [vis, setVis] = useState<Record<string, boolean>>(DEFAULT_VIS);
  const on = (key: string) => vis[key] ?? true;
  const toggle = (key: string) =>
    setVis((current) => ({ ...current, [key]: !(current[key] ?? true) }));

  const p1ce = on('p1.ce');
  const p1pe = on('p1.pe');
  const p1pcr = on('p1.pcr');
  const p2straddle = on('p2.straddle');
  const p2pcr = on('p2.pcr');
  const p3ce = on('p3.ce');
  const p3pe = on('p3.pe');
  const p3pcr = on('p3.pcr');
  const p4ce = on('p4.ce');
  const p4pe = on('p4.pe');
  const p5price = on('p5.price');
  const p5oi = on('p5.oi');
  const p6price = on('p6.price');
  const p6oi = on('p6.oi');

  const theme = useChartTheme();
  const instrument = OI_INSTRUMENTS[instIdx] ?? OI_INSTRUMENTS[0]!;

  function cycle(delta: number) {
    setInstIdx((current) => (current + delta + OI_INSTRUMENTS.length) % OI_INSTRUMENTS.length);
    // A strike that exists on NIFTY means nothing on BANKNIFTY.
    setSelectedStrike(null);
  }

  const historyDate = dataMode === 'historical' ? date : undefined;
  const query = useQuery<StrikeSeriesView>({
    queryKey: [
      'options-lab',
      'strike-series',
      instrument.symbol,
      selectedStrike ?? 'atm',
      dataMode,
      historyDate
    ],
    queryFn: () =>
      getStrikeSeries(instrument.symbol, selectedStrike ?? undefined, { date: historyDate }),
    refetchInterval: dataMode === 'live' ? REFETCH_MS : false
  });

  const vw = query.data;
  const strike = vw?.strike ?? 0;
  const windowMinutes = rangeMinutes === 'all' ? undefined : rangeMinutes;
  // A fresh window or a reset both rebuild the panels (clear + set), which is
  // what snaps the shared zoom back to the chosen range.
  const resetSig = `${zoomNonce}-${rangeMinutes}`;

  // Everything bucketed to the timeframe, once, for all six charts.
  const d = useMemo(() => {
    if (!vw || vw.t.length === 0) return null;
    const keep = bucketIndices(vw.t, timeframe);
    return {
      times: pick(vw.t, keep),
      cePrice: pick(vw.ce_price, keep),
      pePrice: pick(vw.pe_price, keep),
      ceOi: pick(vw.ce_oi, keep),
      peOi: pick(vw.pe_oi, keep),
      ceOiChg: pick(vw.ce_oi_change, keep),
      peOiChg: pick(vw.pe_oi_change, keep),
      straddle: pick(vw.straddle, keep),
      pcr: pick(vw.pcr, keep)
    };
  }, [vw, timeframe]);

  // -- the six chart options ------------------------------------------------
  const priceCvp = useMemo(() => {
    if (!d) return null;
    return buildCallPutOption(
      {
        timestamps: d.times,
        zoomable: true,
        windowMinutes,
        ce: {
          plot: normalizeFromOpen(d.cePrice),
          abs: d.cePrice,
          name: `${strike} CE Price`,
          color: CALL_COLOR
        },
        pe: {
          plot: normalizeFromOpen(d.pePrice),
          abs: d.pePrice,
          name: `${strike} PE Price`,
          color: PUT_COLOR
        },
        normalized: true,
        formatAbs: fmtPrice,
        showCe: p1ce,
        showPe: p1pe,
        pcr: p1pcr ? { values: d.pcr, show: true, format: fmtPcr } : undefined
      },
      theme
    );
  }, [d, strike, p1ce, p1pe, p1pcr, windowMinutes, theme]);

  const straddleChart = useMemo(() => {
    if (!d) return null;
    return buildPriceVsOiOption(
      {
        timestamps: d.times,
        zoomable: true,
        windowMinutes,
        price: d.straddle,
        oi: d.pcr,
        formatPrice: fmtPrice,
        formatOi: fmtPcr,
        showPrice: p2straddle,
        showOi: p2pcr,
        priceColor: STRADDLE_COLOR,
        priceName: 'Straddle',
        oiName: 'PCR'
      },
      theme
    );
  }, [d, p2straddle, p2pcr, windowMinutes, theme]);

  const oiCvp = useMemo(() => {
    if (!d) return null;
    return buildCallPutOption(
      {
        timestamps: d.times,
        zoomable: true,
        windowMinutes,
        ce: {
          plot: normalizeFromOpen(d.ceOi),
          abs: d.ceOi,
          name: `${strike} CE OI`,
          color: CALL_COLOR
        },
        pe: {
          plot: normalizeFromOpen(d.peOi),
          abs: d.peOi,
          name: `${strike} PE OI`,
          color: PUT_COLOR
        },
        normalized: true,
        formatAbs: (v) => fmtOi(v),
        showCe: p3ce,
        showPe: p3pe,
        pcr: p3pcr ? { values: d.pcr, show: true, format: fmtPcr } : undefined
      },
      theme
    );
  }, [d, strike, p3ce, p3pe, p3pcr, windowMinutes, theme]);

  const oiChangeCvp = useMemo(() => {
    if (!d) return null;
    return buildCallPutOption(
      {
        timestamps: d.times,
        zoomable: true,
        windowMinutes,
        ce: { plot: d.ceOiChg, abs: d.ceOiChg, name: `${strike} CE OI Change`, color: CALL_COLOR },
        pe: { plot: d.peOiChg, abs: d.peOiChg, name: `${strike} PE OI Change`, color: PUT_COLOR },
        normalized: false,
        formatAbs: (v) => fmtOi(v),
        showCe: p4ce,
        showPe: p4pe
      },
      theme
    );
  }, [d, strike, p4ce, p4pe, windowMinutes, theme]);

  const cePvo = useMemo(() => {
    if (!d) return null;
    return buildPriceVsOiOption(
      {
        timestamps: d.times,
        zoomable: true,
        windowMinutes,
        price: d.cePrice,
        oi: d.ceOi,
        formatPrice: fmtPrice,
        formatOi: (v) => fmtOi(v),
        showPrice: p5price,
        showOi: p5oi,
        priceColor: CALL_COLOR,
        priceName: `${strike} CE Price`,
        oiName: 'CE OI'
      },
      theme
    );
  }, [d, strike, p5price, p5oi, windowMinutes, theme]);

  const pePvo = useMemo(() => {
    if (!d) return null;
    return buildPriceVsOiOption(
      {
        timestamps: d.times,
        zoomable: true,
        windowMinutes,
        price: d.pePrice,
        oi: d.peOi,
        formatPrice: fmtPrice,
        formatOi: (v) => fmtOi(v),
        showPrice: p6price,
        showOi: p6oi,
        priceColor: PUT_COLOR,
        priceName: `${strike} PE Price`,
        oiName: 'PE OI'
      },
      theme
    );
  }, [d, strike, p6price, p6oi, windowMinutes, theme]);

  // -- live clock -----------------------------------------------------------
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(t);
  }, []);
  const updatedAt = query.dataUpdatedAt;
  const isStale = dataMode === 'live' && Boolean(updatedAt) && now - updatedAt > STALE_AFTER_MS;

  return (
    <div className={s.page}>
      {query.isError ? (
        <div className={s.banner} role="alert">
          <span>Couldn’t load the Price vs OI charts.</span>
          <button type="button" onClick={() => void query.refetch()}>
            Retry
          </button>
        </div>
      ) : !vw && query.isPending ? (
        <div className={cx(s.panel, s.muted)}>Loading Price vs OI…</div>
      ) : vw && vw.data_quality === 'empty' ? (
        <div className={cx(s.panel, s.emptyPanel)}>
          <HistoryMode mode={dataMode} date={date} onMode={setDataMode} onDate={setDate} />
          <p className={s.muted}>
            {dataMode === 'historical'
              ? 'No session archived for that date.'
              : 'No option data recorded for today yet — the charts fill in as the ingest worker captures the chain.'}
          </p>
        </div>
      ) : vw && d ? (
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
                    <p className={s.subLabel}>Expiry</p>
                    <div className={s.select}>
                      <span>{expiryLabel(vw.expiry_date)}</span>
                      <span className={s.caret} aria-hidden="true">
                        <IconChevronDown />
                      </span>
                    </div>
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

                <p className={s.subLabel}>Time Range</p>
                <div className={s.ranges} role="group" aria-label="Time range">
                  {RANGES.map((r) => (
                    <button
                      key={String(r.value)}
                      type="button"
                      className={cx(s.rangeChip, rangeMinutes === r.value && s.active)}
                      aria-pressed={rangeMinutes === r.value}
                      onClick={() => setRangeMinutes(r.value)}
                    >
                      {r.label}
                    </button>
                  ))}
                </div>

                <p className={s.subLabel}>Select Strike</p>
                <div className={s.strikeList}>
                  <div className={s.strikeCol}>Strike</div>
                  {vw.strikes.map((st) => (
                    <button
                      key={st}
                      type="button"
                      className={cx(s.strikeRow, st === strike && s.active)}
                      aria-pressed={st === strike}
                      onClick={() => setSelectedStrike(st)}
                    >
                      {st}
                      {st === strike ? (
                        <span className={s.strikeCheck} aria-hidden="true">
                          <IconCheck />
                        </span>
                      ) : null}
                    </button>
                  ))}
                </div>

                <p className={s.hint}>
                  All panels move together: pick a <strong>Time Range</strong> above, hover any
                  panel for a shared crosshair, <strong>scroll</strong> over a plot to zoom the
                  clock, drag inside it to pan, or drag the <strong>time axis</strong> itself to
                  stretch and squeeze the window.
                </p>
              </section>
            </aside>
          ) : (
            <button
              type="button"
              className={s.restore}
              aria-label="Show settings"
              onClick={() => setSidebarOpen(true)}
            >
              »
            </button>
          )}

          {/* RIGHT MAIN — six charts */}
          <div className={s.grid}>
            <ChartPanel
              group={CHART_GROUP}
              resetSig={resetSig}
              title="Price (Call vs Put)"
              option={priceCvp}
              badge={
                <>
                  <button
                    type="button"
                    className={s.zoomReset}
                    onClick={() => {
                      setRangeMinutes('all');
                      setZoomNonce((n) => n + 1);
                    }}
                    title="Reset every panel to the full session"
                  >
                    ⤢ Reset zoom
                  </button>
                  <LiveBadge
                    dataMode={dataMode}
                    now={now}
                    date={date}
                    updatedAt={updatedAt}
                    fetching={query.isFetching}
                    stale={isStale}
                  />
                </>
              }
              legend={
                <>
                  <Toggle
                    label={`${strike} CE Price`}
                    color={CALL_COLOR}
                    on={p1ce}
                    onToggle={() => toggle('p1.ce')}
                  />
                  <Toggle
                    label={`${strike} PE Price`}
                    color={PUT_COLOR}
                    on={p1pe}
                    onToggle={() => toggle('p1.pe')}
                  />
                  <Toggle label="PCR" dotted on={p1pcr} onToggle={() => toggle('p1.pcr')} />
                </>
              }
            />

            <ChartPanel
              group={CHART_GROUP}
              resetSig={resetSig}
              title={`${strike} - Straddle Price + PCR`}
              option={straddleChart}
              legend={
                <>
                  <Toggle
                    label="Straddle Price"
                    color={STRADDLE_COLOR}
                    on={p2straddle}
                    onToggle={() => toggle('p2.straddle')}
                  />
                  <Toggle label="PCR" dotted on={p2pcr} onToggle={() => toggle('p2.pcr')} />
                </>
              }
            />

            <ChartPanel
              group={CHART_GROUP}
              resetSig={resetSig}
              title="OI (Call vs Put)"
              option={oiCvp}
              legend={
                <>
                  <Toggle
                    label={`${strike} CE OI`}
                    color={CALL_COLOR}
                    on={p3ce}
                    onToggle={() => toggle('p3.ce')}
                  />
                  <Toggle
                    label={`${strike} PE OI`}
                    color={PUT_COLOR}
                    on={p3pe}
                    onToggle={() => toggle('p3.pe')}
                  />
                  <Toggle label="PCR" dotted on={p3pcr} onToggle={() => toggle('p3.pcr')} />
                </>
              }
            />

            <ChartPanel
              group={CHART_GROUP}
              resetSig={resetSig}
              title="OI Change (Call vs Put)"
              option={oiChangeCvp}
              legend={
                <>
                  <Toggle
                    label={`${strike} CE OI Change`}
                    color={CALL_COLOR}
                    on={p4ce}
                    onToggle={() => toggle('p4.ce')}
                  />
                  <Toggle
                    label={`${strike} PE OI Change`}
                    color={PUT_COLOR}
                    on={p4pe}
                    onToggle={() => toggle('p4.pe')}
                  />
                </>
              }
            />

            <ChartPanel
              group={CHART_GROUP}
              resetSig={resetSig}
              title={`${strike} CE - Price vs OI`}
              option={cePvo}
              legend={
                <>
                  <Toggle
                    label={`${strike} CE Price`}
                    color={CALL_COLOR}
                    on={p5price}
                    onToggle={() => toggle('p5.price')}
                  />
                  <Toggle label="CE OI" dotted on={p5oi} onToggle={() => toggle('p5.oi')} />
                </>
              }
            />

            <ChartPanel
              group={CHART_GROUP}
              resetSig={resetSig}
              title={`${strike} PE - Price vs OI`}
              option={pePvo}
              legend={
                <>
                  <Toggle
                    label={`${strike} PE Price`}
                    color={PUT_COLOR}
                    on={p6price}
                    onToggle={() => toggle('p6.price')}
                  />
                  <Toggle label="PE OI" dotted on={p6oi} onToggle={() => toggle('p6.oi')} />
                </>
              }
            />
          </div>
        </div>
      ) : null}
    </div>
  );
}

/** One chart panel: a titled card with a legend row and an ECharts canvas. */
function ChartPanel({
  title,
  option,
  legend,
  badge,
  group,
  resetSig
}: {
  title: string;
  option: EChartsCoreOption | null;
  legend: ReactNode;
  badge?: ReactNode;
  /** The `echarts.connect` group that links this panel to its siblings. */
  group: string;
  /** Changing this rebuilds the panel — the range change and the zoom reset. */
  resetSig: string;
}) {
  return (
    <section className={s.panel}>
      {/* Title and legend are the same kind of thing — what this panel is
          showing — so they share one row, and only the zoom/live badge is set
          apart at the far end. */}
      <div className={s.chartTop}>
        <div className={s.chartTopLeft}>
          <h2 className={s.pTitle}>
            <span className={s.ico} aria-hidden="true">
              <IconChart />
            </span>{' '}
            {title}
          </h2>
          <div className={s.legend}>{legend}</div>
        </div>
        {badge ? <div className={s.chartTopRight}>{badge}</div> : null}
      </div>
      {option == null ? (
        <p className={s.empty}>No captures recorded for this session yet.</p>
      ) : (
        <EChart
          option={option}
          resetKey={`${title}-${resetSig}`}
          group={group}
          className={s.chart}
        />
      )}
    </section>
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
    <button
      type="button"
      className={cx(s.entry, !on && s.off)}
      aria-pressed={on}
      onClick={onToggle}
    >
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

/** The live/archived clock + freshness pill shown on the Price panel. */
function LiveBadge({
  dataMode,
  now,
  date,
  updatedAt,
  fetching,
  stale
}: {
  dataMode: Mode;
  now: number;
  date: string;
  updatedAt: number;
  fetching: boolean;
  stale: boolean;
}) {
  return (
    <span className={cx(s.live, stale && s.stale)}>
      <span className={cx(s.dot, dataMode === 'live' && fetching && s.pulse)} />
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
  );
}
