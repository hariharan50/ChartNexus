import { useQuery } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';
import { cx } from '$shared/ui/cx';
import IconChart from '$shared/ui/icons/IconChart';
import IconChevronDown from '$shared/ui/icons/IconChevronDown';
import BarPair from './components/BarPair';
import OpenInterestChart from './components/OpenInterestChart';
import PcrDonut from './components/PcrDonut';
import SentimentDonut from './components/SentimentDonut';
import TimeRangeSlider from './components/TimeRangeSlider';
import {
  baselineIndex,
  deriveBars,
  fmtOi,
  fmtSigned,
  getOpenInterest,
  inferStep,
  OI_INSTRUMENTS,
  timeLabel,
  windowTotals,
  withinWindow,
  type OiMode,
  type OiView
} from './oi-data';
import s from './route.module.css';
import type { Route } from './+types/route';

export const meta: Route.MetaFunction = () => [{ title: 'Open Interest · Options Lab' }];

const MODES: { key: OiMode; label: string }[] = [
  { key: 'change_total', label: 'OI Change+Total' },
  { key: 'change', label: 'OI Change' },
  { key: 'total', label: 'Total OI' }
];
const STRIKE_FILTERS: { label: string; value: 'all' | number }[] = [
  { label: 'All', value: 'all' },
  { label: 'ATM', value: 2 },
  { label: '5', value: 5 },
  { label: '10', value: 10 },
  { label: '20', value: 20 }
];
const QUICK_RANGES: { label: string; value: number | 'all' }[] = [
  { label: 'Last 3 min', value: 3 },
  { label: 'Last 5 min', value: 5 },
  { label: 'Last 10 min', value: 10 },
  { label: 'Last 15 min', value: 15 },
  { label: 'Last 30 min', value: 30 },
  { label: 'Last 1 hr', value: 60 },
  { label: 'Last 2 hr', value: 120 },
  { label: 'Last 3 hr', value: 180 },
  { label: 'All', value: 'all' }
];

export default function OpenInterest() {
  const [instIdx, setInstIdx] = useState(0);
  const [mode, setMode] = useState<OiMode>('change_total');
  const [showLot, setShowLot] = useState(false);
  const [strikeFilter, setStrikeFilter] = useState<'all' | number>(10);
  /** Which quick-range pill (if any) matches the current window, for highlighting. */
  const [activePreset, setActivePreset] = useState<number | 'all' | null>('all');
  /** Left (window-start) handle position, or -1 for "start of session". */
  const [openFrameIdx, setOpenFrameIdx] = useState(-1);
  /** Right (window-end) handle position, or -1 to follow live (far right). */
  const [nowFrameIdx, setNowFrameIdx] = useState(-1);

  const instrument = OI_INSTRUMENTS[instIdx] ?? OI_INSTRUMENTS[0]!;

  function cycle(delta: number) {
    setInstIdx((current) => (current + delta + OI_INSTRUMENTS.length) % OI_INSTRUMENTS.length);
    setOpenFrameIdx(-1);
    setNowFrameIdx(-1);
    setActivePreset('all');
  }

  const query = useQuery<OiView>({
    queryKey: ['options-lab', 'oi', instrument.symbol],
    queryFn: () => getOpenInterest(instrument.symbol),
    refetchInterval: 15_000
  });

  const view = query.data;
  const lotSize = view?.lot_size ?? 75;

  // -- client re-derivation -------------------------------------------------
  const strikes = useMemo(() => (view ? view.strikes.map((r) => r.strike) : []), [view]);
  const step = useMemo(() => inferStep(strikes), [strikes]);
  const visible = useMemo(
    () =>
      view
        ? withinWindow(strikes, view.atm_strike, step, strikeFilter === 'all' ? 0 : strikeFilter)
        : [],
    [view, strikes, step, strikeFilter]
  );

  const series = useMemo(() => view?.series ?? [], [view]);
  const hasSeries = series.length >= 2;
  // Two frames is enough to drag — the window still collapses and the chart
  // still redraws. Below that there is genuinely nothing to move between.
  const canScrub = series.length >= 2;
  // Until intraday snapshots accumulate the API sends only the two endpoints,
  // so the timeline is coarse rather than broken. Worth saying, not disabling.
  const thinHistory = series.length < 3;
  const lastIdx = Math.max(0, series.length - 1);
  const nowIdx = nowFrameIdx < 0 ? lastIdx : Math.min(nowFrameIdx, lastIdx);
  const openIdx = Math.min(openFrameIdx < 0 ? 0 : Math.min(openFrameIdx, lastIdx), nowIdx);

  const nowFrame = hasSeries ? series[nowIdx] : undefined;
  const openFrame = hasSeries ? series[openIdx] : undefined;

  const bars = useMemo(
    () => (view ? deriveBars(view, visible, openFrame, nowFrame) : []),
    [view, visible, openFrame, nowFrame]
  );
  const totals = useMemo(
    () => (view ? windowTotals(view, openFrame, nowFrame) : undefined),
    [view, openFrame, nowFrame]
  );

  const openLabel =
    nowFrame && openFrame ? timeLabel(openFrame.t) : view ? timeLabel(view.open_ts) : '—';
  const nowLabel = nowFrame ? timeLabel(nowFrame.t) : view ? timeLabel(view.now_ts) : '—';

  const expiryLabel = useMemo(() => {
    if (!view?.expiry_date) return 'Nearest expiry';
    const d = new Date(view.expiry_date);
    const days = Math.max(0, Math.round((d.getTime() - Date.now()) / 86_400_000));
    const label = new Intl.DateTimeFormat('en-GB', {
      day: '2-digit',
      month: 'short',
      year: 'numeric'
    }).format(d);
    return `${label} (${days === 0 ? 'today' : `${days}d`})`;
  }, [view?.expiry_date]);

  function resetSlider() {
    setOpenFrameIdx(-1);
    setNowFrameIdx(-1);
    setActivePreset('all');
  }

  /** A quick-range pill sets the start handle relative to *now*, live. */
  function applyPreset(value: number | 'all') {
    setActivePreset(value);
    setNowFrameIdx(-1);
    if (!hasSeries) return;
    setOpenFrameIdx(value === 'all' ? -1 : baselineIndex(series, lastIdx, value));
  }

  function onOpenHandleChange(idx: number) {
    setActivePreset(null);
    setOpenFrameIdx(idx);
  }

  function onNowHandleChange(idx: number) {
    setActivePreset(null);
    setNowFrameIdx(idx === lastIdx ? -1 : idx);
  }

  // -- live clock -----------------------------------------------------------
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);
  const clock = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Asia/Kolkata',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false
  }).format(now);

  return (
    <div className={s.page}>
      {query.isError ? (
        <div className={s.banner} role="alert">
          <span>Couldn’t load open interest.</span>
          <button type="button" onClick={() => void query.refetch()}>
            Retry
          </button>
        </div>
      ) : !view && query.isPending ? (
        <div className={cx(s.panel, s.muted)}>Loading Open Interest…</div>
      ) : view && view.data_quality === 'empty' ? (
        <div className={cx(s.panel, s.muted)}>No option-chain data available yet.</div>
      ) : view && totals ? (
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
                <button type="button" className={cx(s.seg, s.active)}>
                  Live
                </button>
                <button
                  type="button"
                  className={s.seg}
                  disabled
                  title="Historical mode coming soon"
                >
                  Historical
                </button>
              </div>

              <p className={s.subLabel}>Expiry</p>
              <div className={s.select}>
                <span>{expiryLabel}</span>
                <span className={s.caret} aria-hidden="true">
                  <IconChevronDown />
                </span>
              </div>
              <p className={s.hint}>Live chain is served for the nearest expiry.</p>

              <p className={s.subLabel}>Strikes above-below ATM</p>
              <div className={s.filterRow}>
                {STRIKE_FILTERS.map((f) => (
                  <button
                    key={f.label}
                    type="button"
                    className={cx(s.chip, strikeFilter === f.value && s.active)}
                    onClick={() => setStrikeFilter(f.value)}
                  >
                    {f.label}
                  </button>
                ))}
              </div>
            </section>

            <section className={s.panel}>
              <h2 className={s.pTitle}>
                <span className={s.ico}>
                  <IconChart />
                </span>{' '}
                Market Sentiment <span className={s.dim}>(based on OI)</span>
              </h2>
              <SentimentDonut label={view.sentiment.label} percent={view.sentiment.bullish_pct} />

              <div className={s.pcrLine}>
                PCR: <strong>{totals.pcr.toFixed(2)}</strong>{' '}
                <span className={cx(totals.pcrChange >= 0 ? s.up : s.down)}>
                  ({totals.pcrChange >= 0 ? '+' : ''}
                  {totals.pcrChange.toFixed(2)})
                </span>
              </div>

              <div className={s.insightBox}>
                <p className={s.ibTitle}>ⓘ Market Insight</p>
                <p className={s.ibBody}>{view.sentiment.insight}</p>
              </div>
              <div className={s.analysisBox}>
                <p className={s.abTitle}>ⓘ Analysis</p>
                <p className={s.abBody}>{view.sentiment.analysis}</p>
              </div>
            </section>
          </aside>

          {/* RIGHT MAIN */}
          <div className={s.main}>
            <section className={cx(s.panel, s.chartPanel)}>
              <div className={s.chartTop}>
                <div className={s.modeTabs}>
                  {MODES.map((m) => (
                    <button
                      key={m.key}
                      type="button"
                      className={cx(s.pill, mode === m.key && s.active)}
                      onClick={() => setMode(m.key)}
                    >
                      {m.label}
                    </button>
                  ))}
                </div>
                <div className={s.chartTopRight}>
                  <label className={s.showLot}>
                    <span>Show Lot</span>
                    <input
                      type="checkbox"
                      checked={showLot}
                      onChange={(e) => setShowLot(e.currentTarget.checked)}
                    />
                    <span className={cx(s.switch, showLot && s.on)}>
                      <span className={s.knob} />
                    </span>
                  </label>
                  <span className={s.live}>
                    <span className={cx(s.dot, query.isFetching && s.pulse)} />
                    Live — {clock} IST
                  </span>
                </div>
              </div>

              <OpenInterestChart
                bars={bars}
                mode={mode}
                spot={view.spot}
                maxPain={view.max_pain}
                showLot={showLot}
                lotSize={lotSize}
                showTooltip={true}
                openLabel={openLabel}
                nowLabel={nowLabel}
              />

              <div className={s.legend}>
                <span>
                  <i className={cx(s.sw, s.call, s.solid)} /> Call OI
                </span>
                <span>
                  <i className={cx(s.sw, s.call, s.outline)} /> Call OI Decrease
                </span>
                <span>
                  <i className={cx(s.sw, s.call, s.hatch)} /> Call OI Increase
                </span>
                <span>
                  <i className={cx(s.sw, s.put, s.solid)} /> Put OI
                </span>
                <span>
                  <i className={cx(s.sw, s.put, s.outline)} /> Put OI Decrease
                </span>
                <span>
                  <i className={cx(s.sw, s.put, s.hatch)} /> Put OI Increase
                </span>
              </div>

              {/* time slider */}
              <div className={s.sliderRow}>
                {canScrub ? (
                  <button type="button" className={s.reset} onClick={resetSlider}>
                    Reset
                  </button>
                ) : null}
                <span className={s.end}>{openLabel}</span>
                <TimeRangeSlider
                  min={0}
                  max={lastIdx}
                  openIndex={openIdx}
                  nowIndex={nowIdx}
                  disabled={!canScrub}
                  onOpenChange={onOpenHandleChange}
                  onNowChange={onNowHandleChange}
                />
                <span className={s.end}>{nowLabel}</span>
              </div>

              <div className={s.quick}>
                {QUICK_RANGES.map((q) => (
                  <button
                    key={q.label}
                    type="button"
                    className={cx(s.pill, s.sm, activePreset === q.value && s.active)}
                    disabled={!canScrub}
                    onClick={() => applyPreset(q.value)}
                  >
                    {q.label}
                  </button>
                ))}
              </div>

              <p className={s.caption}>
                Showing OI build-up from {openLabel} to {nowLabel}. Drag either handle to set the
                window.{' '}
                {thinHistory
                  ? "Only the session's two end points have been recorded so far, so the timeline is coarse — it fills in as snapshots accumulate through market hours. "
                  : ''}
                {view.data_quality === 'live_proxy'
                  ? '(open estimated from day-over-day OI change)'
                  : ''}
              </p>
            </section>

            <div className={s.summary}>
              <section className={cx(s.panel, s.sc)}>
                <h3>
                  <span className={s.ico}>
                    <IconChart />
                  </span>{' '}
                  Open Interest Change
                </h3>
                <BarPair
                  callValue={totals.callChg}
                  putValue={totals.putChg}
                  callLabel={fmtSigned(totals.callChg, showLot, lotSize)}
                  putLabel={fmtSigned(totals.putChg, showLot, lotSize)}
                />
              </section>
              <section className={cx(s.panel, s.sc)}>
                <h3>
                  <span className={s.ico}>
                    <IconChart />
                  </span>{' '}
                  Total Open Interest
                </h3>
                <BarPair
                  callValue={totals.callNow}
                  putValue={totals.putNow}
                  callLabel={fmtOi(totals.callNow, showLot, lotSize)}
                  putLabel={fmtOi(totals.putNow, showLot, lotSize)}
                />
              </section>
              <section className={cx(s.panel, s.sc)}>
                <h3>
                  <span className={s.ico}>
                    <IconChart />
                  </span>{' '}
                  Put/Call Ratio
                </h3>
                <PcrDonut pcr={totals.pcr} callNow={totals.callNow} putNow={totals.putNow} />
              </section>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
