import { useQuery } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';
import EChart from '$shared/charts/EChart';
import { buildIvHvIvpOption, type IvHvIvpVisible } from '$shared/charts/options/iv-hv-ivp';
import { useChartTheme } from '$shared/charts/theme/use-chart-theme';
import { cx } from '$shared/ui/cx';
import Select from '$shared/ui/Select';
import IconChart from '$shared/ui/icons/IconChart';
import IconEye from '$shared/ui/icons/IconEye';
import IconEyeOff from '$shared/ui/icons/IconEyeOff';
import {
  buildRows,
  clockLabel,
  coverageNote,
  csvFilename,
  dailyBars,
  dateLabel,
  dayLabel,
  DEFAULT_HV_WINDOW,
  DEFAULT_RANGE,
  fetchDays,
  fmtIv,
  fmtPrice,
  freshnessLabel,
  getHistory,
  getIvHistory,
  hvSessions,
  HV_WINDOWS,
  ivHvIvpCsv,
  OI_INSTRUMENTS,
  rangeDays,
  RANGES,
  REFETCH_MS,
  STALE_AFTER_MS,
  trimToRange,
  type HistoryView,
  type HvWindowKey,
  type IvHistoryView,
  type RangeKey
} from './iv-hv-ivp-data';
import s from './route.module.css';
import type { Route } from './+types/route';

export const meta: Route.MetaFunction = () => [{ title: 'IV/HV/IVP Chart · Options Lab' }];

/**
 * One colour per series, shared by the legend, the plot and the tooltip.
 *
 * IV takes the app's blue because it is the subject. HV and RV are warm and
 * near each other on purpose — they measure the same thing two ways, and the
 * reader should see them as a pair. The two percentiles are cooler still, since
 * they are a different unit sharing the axis.
 */
const COLORS: Record<keyof IvHvIvpVisible, string> = {
  iv: '#3b82f6',
  hv: '#f97316',
  rv: '#a855f7',
  ivr: '#eab308',
  ivp: '#14b8a6',
  price: '#94a3b8'
};

const LABELS: Record<keyof IvHvIvpVisible, string> = {
  iv: 'IV',
  hv: 'HV',
  rv: 'RV',
  ivr: 'IVR',
  ivp: 'IVP',
  price: 'Index Price'
};

/** The legend's order, which is the reference's. */
const SERIES_ORDER = ['iv', 'hv', 'rv', 'ivr', 'ivp', 'price'] as const;

export default function IvHvIvpChart() {
  const [instIdx, setInstIdx] = useState(0);
  const [range, setRange] = useState<RangeKey>(DEFAULT_RANGE);
  const [hvWindow, setHvWindow] = useState<HvWindowKey>(DEFAULT_HV_WINDOW);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  // Bumped by Reset zoom: it feeds `resetKey`, and a rebuild is what
  // re-applies the option's own window — the merge path deliberately leaves
  // the reader's zoom alone (see `use-echart.ts`).
  const [zoomNonce, setZoomNonce] = useState(0);
  /** Which lines are drawn. IV and the index are on, as the reference opens. */
  const [visible, setVisible] = useState<IvHvIvpVisible>({
    iv: true,
    hv: false,
    rv: false,
    ivr: false,
    ivp: false,
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
   * HV and RV cannot report until their window has filled, so asking for
   * exactly the range on screen leaves the first weeks of every chart blank —
   * and at a short range with a long window, nearly all of it. The extra
   * history is computed over and then trimmed away.
   */
  const fetch = fetchDays(days, hvSpan);

  // Two payloads on one axis: a full range of daily index bars, and however
  // many sessions of IV the archive has accrued.
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
    () =>
      trimToRange(
        buildRows(bars, ivHistory.data?.sessions ?? [], {
          hvWindow: hvSpan,
          ivWindow: countSessions(days)
        }),
        days
      ),
    [bars, ivHistory.data, hvSpan, days]
  );

  const option = useMemo(
    () =>
      buildIvHvIvpOption(
        {
          rows,
          visible,
          colors: COLORS,
          formatPrice: fmtPrice,
          formatIv: fmtIv,
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
  const note = coverageNote(ivHistory.data, countSessions(days));

  function download() {
    if (rows.length === 0) return;
    const blob = new Blob([ivHvIvpCsv(rows)], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = csvFilename(instrument.symbol, rows);
    link.click();
    URL.revokeObjectURL(url);
  }

  function toggle(key: keyof IvHvIvpVisible) {
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
        <div className={cx(s.panel, s.muted)}>Loading IV/HV/IVP Chart…</div>
      ) : rows.length === 0 ? (
        <div className={cx(s.panel, s.emptyPanel)}>
          <p className={s.muted}>
            No daily history available for {instrument.short} yet — the price series is what this
            chart is built on.
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

                <p className={s.subLabel}>IVP/IVR Range</p>
                <Select
                  className={s.selectNative}
                  value={range}
                  ariaLabel="IVP and IVR range"
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
                  HV is the annualised close-to-close move over that window. RV reads each day’s own
                  high and low instead, so the two part company when the movement happened inside
                  the sessions rather than between them.
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
                    IV/HV/IVP Chart
                  </h2>

                  <div className={s.legend}>
                    {SERIES_ORDER.map((key) => (
                      <Toggle
                        key={key}
                        label={LABELS[key]}
                        color={COLORS[key]}
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
                Implied volatility at the money against what the index actually did, session by
                session. IVR places today between the window’s low and high; IVP counts how many of
                its sessions sat below today.
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

/**
 * Trading sessions in a calendar window.
 *
 * The ranges are calendar spans because that is how a trader says them — "one
 * year" — but IVR and IVP count *sessions*, and a year holds about 252 of them.
 */
function countSessions(calendarDays: number): number {
  return Math.max(1, Math.round((calendarDays * 252) / 365));
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
