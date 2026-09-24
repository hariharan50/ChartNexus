import { useQuery } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';
import EChart from '$shared/charts/EChart';
import { buildMaxPainOption } from '$shared/charts/options/max-pain';
import { useChartTheme } from '$shared/charts/theme/use-chart-theme';
import { cx } from '$shared/ui/cx';
import IconChart from '$shared/ui/icons/IconChart';
import IconChevronDown from '$shared/ui/icons/IconChevronDown';
import { lastTradingDayIST } from '$shared/formatting/ist-clock';
import HistoryMode, { type Mode } from '../components/HistoryMode';
import IntradayMaxPain from './components/IntradayMaxPain';
import MaxPainSentiment from './components/MaxPainSentiment';
import {
  CALL_COLOR,
  clockLabel,
  dateLabel,
  getOpenInterest,
  inferStep,
  OI_INSTRUMENTS,
  PUT_COLOR,
  REFETCH_MS,
  withinWindow,
  type OiView
} from '../open-interest/oi-data';
import {
  fmtPain,
  getMaxPainSeries,
  maxPainBias,
  painCurve,
  visibleCurve,
  windowWidened,
  type MaxPainSeriesView
} from './max-pain-data';
import s from './route.module.css';
import type { Route } from './+types/route';

export const meta: Route.MetaFunction = () => [{ title: 'Max Pain · MarketCompass' }];

/** No ±2 setting: a five-bar pain profile has no readable shape. */
const STRIKE_FILTERS: { label: string; value: 'all' | number }[] = [
  { label: 'All', value: 'all' },
  { label: '5', value: 5 },
  { label: '10', value: 10 },
  { label: '20', value: 20 }
];

export default function MaxPain() {
  const [instIdx, setInstIdx] = useState(0);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [mode, setMode] = useState<Mode>('live');
  const [date, setDate] = useState(lastTradingDayIST);
  const [strikeFilter, setStrikeFilter] = useState<'all' | number>(20);
  const theme = useChartTheme();

  const instrument = OI_INSTRUMENTS[instIdx] ?? OI_INSTRUMENTS[0]!;

  // The same endpoint the Open Interest page reads — a shared query key, so the
  // two pages share one cached payload rather than polling it twice (they share
  // it whenever both are in the same mode/day).
  const historyDate = mode === 'historical' ? date : undefined;
  const query = useQuery<OiView>({
    queryKey: ['options-lab', 'oi', instrument.symbol, mode, historyDate],
    queryFn: () => getOpenInterest(instrument.symbol, { date: historyDate }),
    refetchInterval: mode === 'live' ? REFETCH_MS : false
  });

  // The session's max-pain path. A second query rather than a field on the OI
  // payload: it reads the whole archive for the day, which the snapshot
  // endpoint has no business carrying.
  const seriesQuery = useQuery<MaxPainSeriesView>({
    queryKey: ['options-lab', 'max-pain-series', instrument.symbol, mode, historyDate],
    queryFn: () => getMaxPainSeries(instrument.symbol, { date: historyDate }),
    refetchInterval: mode === 'live' ? REFETCH_MS : false
  });

  const view = query.data;

  // -- the curve ------------------------------------------------------------
  const curve = useMemo(() => painCurve(view?.strikes ?? []), [view]);

  const bars = useMemo(() => {
    if (!view || curve.length === 0) return [];
    const strikes = curve.map((point) => point.strike);
    const step = inferStep(strikes);
    const visible = withinWindow(
      strikes,
      view.atm_strike,
      step,
      strikeFilter === 'all' ? 0 : strikeFilter
    );
    return visibleCurve(curve, visible, view.max_pain);
  }, [view, curve, strikeFilter]);

  const widened = useMemo(() => {
    if (!view || curve.length === 0 || strikeFilter === 'all') return false;
    const strikes = curve.map((point) => point.strike);
    const visible = withinWindow(strikes, view.atm_strike, inferStep(strikes), strikeFilter);
    return windowWidened(visible, view.max_pain);
  }, [view, curve, strikeFilter]);

  const option = useMemo(
    () =>
      buildMaxPainOption(
        {
          bars,
          spot: view?.spot ?? 0,
          maxPain: view?.max_pain ?? 0,
          formatPain: fmtPain,
          callColor: CALL_COLOR,
          putColor: PUT_COLOR
        },
        theme
      ),
    [bars, view, theme]
  );

  const bias = useMemo(
    () => maxPainBias(view?.spot ?? Number.NaN, view?.max_pain ?? Number.NaN),
    [view]
  );

  // -- live clock -----------------------------------------------------------
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(t);
  }, []);
  const expiry = useMemo(() => {
    if (!view?.expiry_date) return 'Nearest expiry';
    const date = new Date(view.expiry_date);
    const days = Math.max(0, Math.round((date.getTime() - Date.now()) / 86_400_000));
    const label = new Intl.DateTimeFormat('en-GB', {
      day: '2-digit',
      month: 'short',
      year: 'numeric'
    }).format(date);
    return `${label} (${days === 0 ? 'today' : `${days}d`})`;
  }, [view?.expiry_date]);

  return (
    <div className={s.page}>
      {query.isError ? (
        <div className={s.banner} role="alert">
          <span>Couldn’t load max pain.</span>
          <button type="button" onClick={() => void query.refetch()}>
            Retry
          </button>
        </div>
      ) : !view && query.isPending ? (
        <div className={cx(s.panel, s.muted)}>Loading Max Pain…</div>
      ) : view ? (
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
                    <button
                      type="button"
                      aria-label="Previous"
                      onClick={() =>
                        setInstIdx((i) => (i - 1 + OI_INSTRUMENTS.length) % OI_INSTRUMENTS.length)
                      }
                    >
                      ‹
                    </button>
                    <button
                      type="button"
                      aria-label="Next"
                      onClick={() => setInstIdx((i) => (i + 1) % OI_INSTRUMENTS.length)}
                    >
                      ›
                    </button>
                  </span>
                </div>

                <HistoryMode mode={mode} date={date} onMode={setMode} onDate={setDate} />

                <p className={s.subLabel}>Expiry</p>
                <div className={s.select}>
                  <span>{expiry}</span>
                  <span className={s.caret} aria-hidden="true">
                    <IconChevronDown />
                  </span>
                </div>

                <p className={s.subLabel}>Strikes above and below ATM</p>
                <div className={s.filterRow}>
                  {STRIKE_FILTERS.map((filter) => (
                    <button
                      key={filter.label}
                      type="button"
                      className={cx(s.chip, strikeFilter === filter.value && s.active)}
                      onClick={() => setStrikeFilter(filter.value)}
                    >
                      {filter.label}
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
            {/* The session's path first: where max pain is heading is the live
                story, and the profile below is the snapshot behind it. */}
            <IntradayMaxPain
              view={seriesQuery.data}
              loading={seriesQuery.isPending}
              historical={mode === 'historical'}
            />

            <section className={s.panel}>
              <div className={s.chartTop}>
                <h2 className={s.pTitle}>
                  <span className={s.ico} aria-hidden="true">
                    <IconChart />
                  </span>{' '}
                  Max Pain
                </h2>
                <span className={s.live}>
                  <span className={cx(s.dot, query.isFetching && s.pulse)} />
                  {dateLabel(now)}, {clockLabel(now)} IST
                </span>
              </div>

              {/* The drawn window, in words. The chart is a canvas, so without
                  this the strike filter gives no readable confirmation of what
                  it did — and it is the one control on the page whose effect is
                  otherwise invisible when the ladder is already narrow. */}
              <p className={s.range}>
                {bars.length > 0
                  ? `Showing ${bars.length} strikes · ${bars[0]!.strike} – ${bars[bars.length - 1]!.strike}`
                  : 'Showing no strikes'}
                <span className={s.sep} aria-hidden="true">
                  {' · '}
                </span>
                priced against all {curve.length} listed
              </p>

              {bars.length === 0 ? (
                <p className={s.empty}>
                  {mode === 'historical'
                    ? 'No session archived for that date.'
                    : 'No option chain available yet.'}
                </p>
              ) : (
                <>
                  <EChart option={option} className={s.chart} />
                  <div className={s.legend}>
                    <span>
                      <i className={s.sw} style={{ background: CALL_COLOR }} /> Call Pain
                    </span>
                    <span>
                      <i className={s.sw} style={{ background: PUT_COLOR }} /> Put Pain
                    </span>
                  </div>
                </>
              )}

              <p className={s.caption}>
                Pain is what every holder would lose if the market settled at each strike — calls
                below it and puts above it expire worthless.
                {widened
                  ? ' The range was widened past the chosen filter so the max-pain strike stays on the chart.'
                  : ''}
              </p>
            </section>

            <section className={s.panel}>
              <h2 className={s.pTitle}>
                <span className={s.ico} aria-hidden="true">
                  <IconChart />
                </span>{' '}
                Market Sentiment <span className={s.dim}>(based on Max Pain)</span>
              </h2>
              <MaxPainSentiment bias={bias} maxPain={view.max_pain} spot={view.spot} />
            </section>
          </div>
        </div>
      ) : null}
    </div>
  );
}
