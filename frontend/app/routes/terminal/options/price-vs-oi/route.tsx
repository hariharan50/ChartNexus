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

export default function PriceVsOi() {
  const [instIdx, setInstIdx] = useState(0);
  const [dataMode, setDataMode] = useState<Mode>('live');
  const [date, setDate] = useState(lastTradingDayIST);
  const [timeframe, setTimeframe] = useState<Timeframe>(DEFAULT_TIMEFRAME);
  const [selectedStrike, setSelectedStrike] = useState<number | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);

  // Series toggles, shared across the panels that draw the same leg.
  const [showCe, setShowCe] = useState(true);
  const [showPe, setShowPe] = useState(true);
  const [showCvpPcr, setShowCvpPcr] = useState(false);
  const [showStraddle, setShowStraddle] = useState(true);
  const [showStraddlePcr, setShowStraddlePcr] = useState(true);
  const [showCeOi, setShowCeOi] = useState(true);
  const [showPeOi, setShowPeOi] = useState(true);

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
        showCe,
        showPe,
        pcr: showCvpPcr ? { values: d.pcr, show: true, format: fmtPcr } : undefined
      },
      theme
    );
  }, [d, strike, showCe, showPe, showCvpPcr, theme]);

  const straddleChart = useMemo(() => {
    if (!d) return null;
    return buildPriceVsOiOption(
      {
        timestamps: d.times,
        price: d.straddle,
        oi: d.pcr,
        formatPrice: fmtPrice,
        formatOi: fmtPcr,
        showPrice: showStraddle,
        showOi: showStraddlePcr,
        priceColor: STRADDLE_COLOR,
        priceName: 'Straddle',
        oiName: 'PCR'
      },
      theme
    );
  }, [d, showStraddle, showStraddlePcr, theme]);

  const oiCvp = useMemo(() => {
    if (!d) return null;
    return buildCallPutOption(
      {
        timestamps: d.times,
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
        showCe,
        showPe,
        pcr: showCvpPcr ? { values: d.pcr, show: true, format: fmtPcr } : undefined
      },
      theme
    );
  }, [d, strike, showCe, showPe, showCvpPcr, theme]);

  const oiChangeCvp = useMemo(() => {
    if (!d) return null;
    return buildCallPutOption(
      {
        timestamps: d.times,
        ce: { plot: d.ceOiChg, abs: d.ceOiChg, name: `${strike} CE OI Change`, color: CALL_COLOR },
        pe: { plot: d.peOiChg, abs: d.peOiChg, name: `${strike} PE OI Change`, color: PUT_COLOR },
        normalized: false,
        formatAbs: (v) => fmtOi(v),
        showCe,
        showPe
      },
      theme
    );
  }, [d, strike, showCe, showPe, theme]);

  const cePvo = useMemo(() => {
    if (!d) return null;
    return buildPriceVsOiOption(
      {
        timestamps: d.times,
        price: d.cePrice,
        oi: d.ceOi,
        formatPrice: fmtPrice,
        formatOi: (v) => fmtOi(v),
        showPrice: showCe,
        showOi: showCeOi,
        priceColor: CALL_COLOR,
        priceName: `${strike} CE Price`,
        oiName: 'CE OI'
      },
      theme
    );
  }, [d, strike, showCe, showCeOi, theme]);

  const pePvo = useMemo(() => {
    if (!d) return null;
    return buildPriceVsOiOption(
      {
        timestamps: d.times,
        price: d.pePrice,
        oi: d.peOi,
        formatPrice: fmtPrice,
        formatOi: (v) => fmtOi(v),
        showPrice: showPe,
        showOi: showPeOi,
        priceColor: PUT_COLOR,
        priceName: `${strike} PE Price`,
        oiName: 'PE OI'
      },
      theme
    );
  }, [d, strike, showPe, showPeOi, theme]);

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
              title="Price (Call vs Put)"
              option={priceCvp}
              badge={
                <LiveBadge
                  dataMode={dataMode}
                  now={now}
                  date={date}
                  updatedAt={updatedAt}
                  fetching={query.isFetching}
                  stale={isStale}
                />
              }
              legend={
                <>
                  <Toggle
                    label={`${strike} CE Price`}
                    color={CALL_COLOR}
                    on={showCe}
                    onToggle={() => setShowCe((v) => !v)}
                  />
                  <Toggle
                    label={`${strike} PE Price`}
                    color={PUT_COLOR}
                    on={showPe}
                    onToggle={() => setShowPe((v) => !v)}
                  />
                  <Toggle
                    label="PCR"
                    dotted
                    on={showCvpPcr}
                    onToggle={() => setShowCvpPcr((v) => !v)}
                  />
                </>
              }
            />

            <ChartPanel
              title={`${strike} - Straddle Price + PCR`}
              option={straddleChart}
              legend={
                <>
                  <Toggle
                    label="Straddle Price"
                    color={STRADDLE_COLOR}
                    on={showStraddle}
                    onToggle={() => setShowStraddle((v) => !v)}
                  />
                  <Toggle
                    label="PCR"
                    dotted
                    on={showStraddlePcr}
                    onToggle={() => setShowStraddlePcr((v) => !v)}
                  />
                </>
              }
            />

            <ChartPanel
              title="OI (Call vs Put)"
              option={oiCvp}
              legend={
                <>
                  <Toggle
                    label={`${strike} CE OI`}
                    color={CALL_COLOR}
                    on={showCe}
                    onToggle={() => setShowCe((v) => !v)}
                  />
                  <Toggle
                    label={`${strike} PE OI`}
                    color={PUT_COLOR}
                    on={showPe}
                    onToggle={() => setShowPe((v) => !v)}
                  />
                  <Toggle
                    label="PCR"
                    dotted
                    on={showCvpPcr}
                    onToggle={() => setShowCvpPcr((v) => !v)}
                  />
                </>
              }
            />

            <ChartPanel
              title="OI Change (Call vs Put)"
              option={oiChangeCvp}
              legend={
                <>
                  <Toggle
                    label={`${strike} CE OI Change`}
                    color={CALL_COLOR}
                    on={showCe}
                    onToggle={() => setShowCe((v) => !v)}
                  />
                  <Toggle
                    label={`${strike} PE OI Change`}
                    color={PUT_COLOR}
                    on={showPe}
                    onToggle={() => setShowPe((v) => !v)}
                  />
                </>
              }
            />

            <ChartPanel
              title={`${strike} CE - Price vs OI`}
              option={cePvo}
              legend={
                <>
                  <Toggle
                    label={`${strike} CE Price`}
                    color={CALL_COLOR}
                    on={showCe}
                    onToggle={() => setShowCe((v) => !v)}
                  />
                  <Toggle
                    label="CE OI"
                    dotted
                    on={showCeOi}
                    onToggle={() => setShowCeOi((v) => !v)}
                  />
                </>
              }
            />

            <ChartPanel
              title={`${strike} PE - Price vs OI`}
              option={pePvo}
              legend={
                <>
                  <Toggle
                    label={`${strike} PE Price`}
                    color={PUT_COLOR}
                    on={showPe}
                    onToggle={() => setShowPe((v) => !v)}
                  />
                  <Toggle
                    label="PE OI"
                    dotted
                    on={showPeOi}
                    onToggle={() => setShowPeOi((v) => !v)}
                  />
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
  badge
}: {
  title: string;
  option: EChartsCoreOption | null;
  legend: ReactNode;
  badge?: ReactNode;
}) {
  return (
    <section className={s.panel}>
      <div className={s.chartTop}>
        <h2 className={s.pTitle}>
          <span className={s.ico} aria-hidden="true">
            <IconChart />
          </span>{' '}
          {title}
        </h2>
        {badge ? <div className={s.chartTopRight}>{badge}</div> : null}
      </div>
      <div className={s.legend}>{legend}</div>
      {option == null ? (
        <p className={s.empty}>No captures recorded for this session yet.</p>
      ) : (
        <EChart option={option} resetKey={title} className={s.chart} />
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
