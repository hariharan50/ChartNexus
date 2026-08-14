import { useQuery } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';
import { buildPriceVsOiOption } from '$shared/charts/options/price-vs-oi';
import EChart from '$shared/charts/EChart';
import { useChartTheme } from '$shared/charts/theme/use-chart-theme';
import DatePicker from '$shared/ui/DatePicker';
import { isoDateIST, lastTradingDayIST } from '$shared/formatting/ist-clock';
import { cx } from '$shared/ui/cx';
import IconChart from '$shared/ui/icons/IconChart';
import IconChevronDown from '$shared/ui/icons/IconChevronDown';
import {
  DEFAULT_INTERVAL,
  expiryLabel,
  feedAgeLabel,
  feedAgeMs,
  fmtOi,
  fmtPrice,
  getPriceOiSeries,
  INSTRUMENTS,
  REFETCH_MS,
  timeLabel,
  type Interval,
  type PriceOiView
} from './price-vs-oi-data';
import s from './price-vs-oi.module.css';
import type { Route } from './+types/price-vs-oi';

export const meta: Route.MetaFunction = () => [
  { title: 'Price vs OI · Future Lab · MarketCompass' }
];

const CHART_GROUP = 'price-oi';
type Mode = 'live' | 'historical';

const INTERVALS: readonly { value: Interval; label: string }[] = [
  { value: '1m', label: '1m' },
  { value: '5m', label: '5m' },
  { value: '15m', label: '15m' },
  { value: '1h', label: '1h' }
];

export default function FuturePriceVsOi() {
  const [instIdx, setInstIdx] = useState(0);
  const [mode, setMode] = useState<Mode>('live');
  const [date, setDate] = useState(lastTradingDayIST);
  const [interval, setInterval] = useState<Interval>(DEFAULT_INTERVAL);
  const [showPrice, setShowPrice] = useState(true);
  const [showOi, setShowOi] = useState(true);

  const instrument = INSTRUMENTS[instIdx] ?? INSTRUMENTS[0];
  const historicalDate = mode === 'historical' ? date : undefined;

  const query = useQuery<PriceOiView>({
    queryKey: ['future-lab', 'price-oi', instrument.symbol, interval, mode, historicalDate],
    queryFn: () =>
      getPriceOiSeries(instrument.symbol, {
        interval,
        ...(historicalDate ? { date: historicalDate } : {})
      }),
    refetchInterval: mode === 'live' ? REFETCH_MS : false
  });

  const view = query.data;
  const theme = useChartTheme();

  const option = useMemo(
    () =>
      view
        ? buildPriceVsOiOption(
            {
              timestamps: view.t,
              price: view.price,
              oi: view.oi,
              formatPrice: fmtPrice,
              formatOi: (value: number) => fmtOi(value),
              showPrice,
              showOi
            },
            theme
          )
        : null,
    [view, showPrice, showOi, theme]
  );

  // -- live clock -----------------------------------------------------------
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(t);
  }, []);
  const clock = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Asia/Kolkata',
    hour: 'numeric',
    minute: '2-digit',
    second: '2-digit',
    hour12: true
  })
    .format(now)
    .toLowerCase();
  // Feed-age only matters for the live tape; a replayed past day is never "stale".
  const feedAge = mode === 'live' ? feedAgeMs(view?.now_ts, now) : null;

  function cycle(delta: number) {
    setInstIdx((current) => (current + delta + INSTRUMENTS.length) % INSTRUMENTS.length);
  }

  return (
    <div className={s.page}>
      {query.isError ? (
        <div className={s.banner} role="alert">
          <span>Couldn’t load the price-vs-OI series.</span>
          <button type="button" onClick={() => void query.refetch()}>
            Retry
          </button>
        </div>
      ) : !view && query.isPending ? (
        <div className={cx(s.panel, s.muted)}>Loading Price vs OI…</div>
      ) : view ? (
        <div className={s.layout}>
          {/* LEFT SIDEBAR */}
          <aside className={s.sidebar}>
            <section className={s.panel}>
              <h2 className={s.pTitle}>Settings</h2>

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

              <p className={s.subLabel}>Select Mode</p>
              <div className={s.modeGrid}>
                <button
                  type="button"
                  className={cx(s.seg, mode === 'live' && s.active)}
                  onClick={() => setMode('live')}
                >
                  Live
                </button>
                <button
                  type="button"
                  className={cx(s.seg, mode === 'historical' && s.active)}
                  onClick={() => setMode('historical')}
                >
                  Historical
                </button>
              </div>

              {mode === 'historical' ? (
                <>
                  <p className={s.subLabel}>Session date</p>
                  <DatePicker
                    value={date}
                    max={isoDateIST(0)}
                    onChange={setDate}
                    ariaLabel="Session date"
                  />
                </>
              ) : null}

              <div className={s.twoUp}>
                <div>
                  <p className={s.subLabel}>Expiry</p>
                  <div className={s.select}>
                    <span>{expiryLabel(view.expiry_date)}</span>
                    <span className={s.caret} aria-hidden="true">
                      <IconChevronDown />
                    </span>
                  </div>
                </div>
                <div>
                  <p className={s.subLabel}>Time</p>
                  <select
                    className={s.selectNative}
                    aria-label="Time interval"
                    value={interval}
                    onChange={(e) => setInterval(e.currentTarget.value as Interval)}
                  >
                    {INTERVALS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
            </section>
          </aside>

          {/* RIGHT MAIN */}
          <div className={s.main}>
            <div className={s.topBar}>
              <h1 className={s.title}>
                <span className={s.ico} aria-hidden="true">
                  <IconChart />
                </span>
                Future Price vs OI
              </h1>
              <span className={cx(s.live, feedAge !== null && s.stale)}>
                <span className={cx(s.dot, mode === 'live' && query.isFetching && s.pulse)} />
                {mode === 'live' ? `${clock} IST` : `Archived · ${date}`}
                {feedAge !== null ? (
                  <>
                    <span className={s.sep} aria-hidden="true">
                      ·
                    </span>
                    <span>{feedAgeLabel(feedAge)}</span>
                  </>
                ) : null}
              </span>
            </div>

            <section className={s.chartPanel}>
              <div className={s.legend}>
                <button
                  type="button"
                  className={cx(s.entry, !showPrice && s.off)}
                  onClick={() => setShowPrice((on) => !on)}
                  aria-pressed={showPrice}
                  style={{ color: showPrice ? '#3b82f6' : undefined }}
                >
                  <Eye on={showPrice} />
                  Price
                </button>
                <button
                  type="button"
                  className={cx(s.entry, !showOi && s.off)}
                  onClick={() => setShowOi((on) => !on)}
                  aria-pressed={showOi}
                >
                  <Eye on={showOi} />
                  <span className={s.dotLine} aria-hidden="true" />
                  OI
                </button>
              </div>

              {view.t.length === 0 || option === null ? (
                <p className={s.empty}>
                  {mode === 'historical'
                    ? 'No session archived for that date.'
                    : 'No snapshots recorded for today yet — the series fills in as the ingest worker captures them.'}
                </p>
              ) : (
                <EChart option={option} className={s.chart} group={CHART_GROUP} />
              )}
            </section>

            <p className={s.caption}>{captionFor(view)}</p>
          </div>
        </div>
      ) : null}
    </div>
  );
}

/** The plain-English note under the chart, from the data tier. */
function captionFor(view: PriceOiView): string {
  if (view.data_quality === 'empty') {
    return 'No snapshots recorded yet — the series fills in as the ingest worker captures them.';
  }
  if (view.data_quality === 'live_proxy') {
    return 'Nothing archived for this day — showing the 9:15 open against the live chain. The shape fills in as snapshots are captured.';
  }
  const first = view.t[0];
  const second = view.t[1] ?? view.t[0];
  if (view.open_is_estimated && first && second) {
    return `The ${timeLabel(first)} baseline is derived from the day’s OI change; recorded history starts at ${timeLabel(second)}. OI is total chain open interest.`;
  }
  return first
    ? `Recorded from ${timeLabel(first)} at ${view.interval} buckets. OI is total chain open interest.`
    : '';
}

/** Open eye when shown, struck through when hidden — matches the Options Lab legend. */
function Eye({ on }: { on: boolean }) {
  return (
    <svg viewBox="0 0 16 16" className={s.eye} aria-hidden="true">
      <path
        d="M1 8s2.5-4.5 7-4.5S15 8 15 8s-2.5 4.5-7 4.5S1 8 1 8Z"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.3"
      />
      <circle cx="8" cy="8" r="1.9" fill="currentColor" />
      {!on ? <path d="M2 14 14 2" stroke="currentColor" strokeWidth="1.3" /> : null}
    </svg>
  );
}
