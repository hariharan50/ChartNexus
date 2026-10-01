import { useQuery } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';
import EChart from '$shared/charts/EChart';
import { buildIvHvOption, type IvHvVisible } from '$shared/charts/options/iv-hv';
import { useChartTheme } from '$shared/charts/theme/use-chart-theme';
import { cx } from '$shared/ui/cx';
import Select from '$shared/ui/Select';
import IconChart from '$shared/ui/icons/IconChart';
import IconEye from '$shared/ui/icons/IconEye';
import IconEyeOff from '$shared/ui/icons/IconEyeOff';
import {
  buildSpreadRows,
  CALL_COLOR,
  clockLabel,
  coverageNote,
  csvFilename,
  dailyBars,
  dateLabel,
  dayLabel,
  DEFAULT_HV_WINDOW,
  fetchDays,
  DEFAULT_SPREAD_RANGE,
  fmtPrice,
  fmtSpread,
  freshnessLabel,
  getHistory,
  getIvHistory,
  hvSessions,
  HV_WINDOWS,
  ivHvCsv,
  OI_INSTRUMENTS,
  PUT_COLOR,
  rangeDays,
  RANGES,
  REFETCH_MS,
  spreadStats,
  STALE_AFTER_MS,
  trimToRange,
  type HistoryView,
  type HvWindowKey,
  type IvHistoryView,
  type RangeKey
} from './iv-hv-data';
import s from './route.module.css';
import type { Route } from './+types/route';

export const meta: Route.MetaFunction = () => [{ title: 'IV - HV · Options Lab' }];

/**
 * The future rides above the index, so it needs its own hue.
 *
 * Not amber: that is `theme.marker`, which the zero rule uses, and a future
 * line the same colour as the zero rule read as one flat series crossing the
 * whole plot. Blue is unclaimed on this page — the bars own green and red.
 */
const FUTURE_COLOR = '#60a5fa';
const PRICE_COLOR = '#94a3b8';

const LABELS: Record<keyof IvHvVisible, string> = {
  spread: 'IV − HV',
  future: 'Future',
  price: 'Index Price'
};

/** The legend's order, which is the reference's. */
const SERIES_ORDER = ['spread', 'future', 'price'] as const;

export default function IvHvChart() {
  const [instIdx, setInstIdx] = useState(0);
  const [range, setRange] = useState<RangeKey>(DEFAULT_SPREAD_RANGE);
  const [hvWindow, setHvWindow] = useState<HvWindowKey>(DEFAULT_HV_WINDOW);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  // Bumped by Reset zoom: it feeds `resetKey`, and a rebuild is what re-applies
  // the option's own window — the merge path deliberately leaves the reader's
  // zoom alone (see `use-echart.ts`).
  const [zoomNonce, setZoomNonce] = useState(0);
  const [visible, setVisible] = useState<IvHvVisible>({
    spread: true,
    future: true,
    price: true
  });

  const theme = useChartTheme();
  const instrument = OI_INSTRUMENTS[instIdx] ?? OI_INSTRUMENTS[0]!;

  function cycle(delta: number) {
    setInstIdx((current) => (current + delta + OI_INSTRUMENTS.length) % OI_INSTRUMENTS.length);
  }

  const days = rangeDays(range);
  const hvSpan = hvSessions(hvWindow);
  /*
   * Fetch past the left edge of what is drawn.
   *
   * HV cannot report until its window has filled, so asking for exactly the
   * range on screen spends the whole range warming up: at Range = 1 Month with
   * a 1-Month window the two are the same length and the series yields a single
   * point. The extra history is computed over and then trimmed away.
   */
  const fetch = fetchDays(days, hvSpan);

  // The same two payloads the IV/HV/IVP page reads, on the same query keys, so
  // moving between the two pages hits a warm cache.
  const history = useQuery<HistoryView>({
    queryKey: ['market', 'history', instrument.symbol, '1d', fetch],
    queryFn: () => getHistory(instrument.symbol, '1d', fetch),
    refetchInterval: REFETCH_MS
  });

  const ivHistory = useQuery<IvHistoryView>({
    queryKey: ['options-lab', 'iv-history', instrument.symbol, fetch],
    queryFn: () => getIvHistory(instrument.symbol, fetch),
    refetchInterval: REFETCH_MS
  });

  const bars = useMemo(() => dailyBars(history.data?.candles ?? []), [history.data]);

  const rows = useMemo(
    () => trimToRange(buildSpreadRows(bars, ivHistory.data?.sessions ?? [], hvSpan), days),
    [bars, ivHistory.data, hvSpan, days]
  );

  const stats = useMemo(() => spreadStats(rows), [rows]);

  const option = useMemo(
    () =>
      buildIvHvOption(
        {
          rows,
          visible,
          callColor: CALL_COLOR,
          putColor: PUT_COLOR,
          futureColor: FUTURE_COLOR,
          priceColor: PRICE_COLOR,
          formatPrice: fmtPrice,
          formatSpread: fmtSpread,
          formatDay: dayLabel,
          zoomable: true
        },
        theme
      ),
    [rows, visible, theme]
  );

  // -- live clock -----------------------------------------------------------
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const updatedAt = Math.max(history.dataUpdatedAt, ivHistory.dataUpdatedAt);
  const isStale = Boolean(updatedAt) && now - updatedAt > STALE_AFTER_MS;
  const isPending = history.isPending || ivHistory.isPending;
  const isError = history.isError || ivHistory.isError;
  const note = coverageNote(ivHistory.data, hvSpan);

  function download() {
    if (rows.length === 0) return;
    const blob = new Blob([ivHvCsv(rows)], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = csvFilename(instrument.symbol, rows);
    link.click();
    URL.revokeObjectURL(url);
  }

  function toggle(key: keyof IvHvVisible) {
    setVisible((current) => ({ ...current, [key]: !current[key] }));
  }

  return (
    <div className={s.page}>
      {isError ? (
        <div className={s.banner} role="alert">
          <span>Couldn’t load the volatility history.</span>
          <button
            type="button"
            onClick={() => {
              void history.refetch();
              void ivHistory.refetch();
            }}
          >
            Retry
          </button>
        </div>
      ) : rows.length === 0 && isPending ? (
        <div className={cx(s.panel, s.muted)}>Loading IV - HV…</div>
      ) : rows.length === 0 ? (
        <div className={cx(s.panel, s.emptyPanel)}>
          <p className={s.muted}>
            No daily history available for {instrument.short} yet — the price series is what the
            historical half of this spread is built from.
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

                <p className={s.subLabel}>Range</p>
                <Select
                  className={s.selectNative}
                  value={range}
                  ariaLabel="Date range"
                  onChange={setRange}
                  options={RANGES.map((entry) => ({ value: entry.value, label: entry.label }))}
                />

                <p className={s.subLabel}>HV Range</p>
                <Select
                  className={s.selectNative}
                  value={hvWindow}
                  ariaLabel="HV range"
                  onChange={setHvWindow}
                  options={HV_WINDOWS.map((entry) => ({ value: entry.value, label: entry.label }))}
                />

                <p className={s.hint}>
                  A green bar means implied volatility sat above what the index actually did —
                  options priced rich. Red means they were cheap against the move that followed.
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
                <div className={s.chartTopLeft}>
                  <h2 className={s.pTitle}>
                    <span className={s.ico} aria-hidden="true">
                      <IconChart />
                    </span>{' '}
                    IV - HV
                  </h2>

                  <div className={s.legend}>
                    {SERIES_ORDER.map((key) => (
                      <Toggle
                        key={key}
                        label={LABELS[key]}
                        color={
                          key === 'spread'
                            ? CALL_COLOR
                            : key === 'future'
                              ? FUTURE_COLOR
                              : PRICE_COLOR
                        }
                        dotted={key === 'price'}
                        on={visible[key]}
                        onToggle={() => toggle(key)}
                      />
                    ))}
                  </div>
                </div>

                <div className={s.chartTopRight}>
                  <span className={cx(s.live, isStale && s.stale)}>
                    <span
                      className={cx(s.dot, (history.isFetching || ivHistory.isFetching) && s.pulse)}
                    />
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
                    className={s.zoomReset}
                    onClick={() => setZoomNonce((n) => n + 1)}
                    title="Back to the whole range"
                  >
                    ⤢ Reset zoom
                  </button>
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

              <EChart
                option={option}
                resetKey={`${instrument.symbol}-${range}-${hvWindow}-${zoomNonce}`}
                className={s.chart}
              />

              <p className={s.caption}>
                {stats.mean === null
                  ? 'No session yet has both an implied and a historical volatility to subtract.'
                  : `${stats.rich} of ${stats.covered} sessions priced rich, ${stats.cheap} cheap, averaging ${fmtSpread(stats.mean)} points.`}{' '}
                A bar is drawn only where both halves are real — an implied volatility with no
                historical volatility behind it is not a premium.
                {note ? ` ${note}` : ''} Scroll over the plot to zoom the dates, drag inside it to
                pan, or drag the date strip itself to stretch and squeeze the window.
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
  color: string;
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
        <span className={s.dash} style={{ color }} aria-hidden="true" />
      ) : (
        <span className={s.swatch} style={{ background: color }} />
      )}
      <span className={s.label}>{label}</span>
    </button>
  );
}
