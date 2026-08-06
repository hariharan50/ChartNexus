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
  axisTicks,
  baselineIndex,
  clockLabel,
  dateLabel,
  deriveBars,
  fmtOi,
  fmtSigned,
  freshnessLabel,
  getOpenInterest,
  inferStep,
  OI_INSTRUMENTS,
  REFETCH_MS,
  STALE_AFTER_MS,
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
    refetchInterval: REFETCH_MS
  });

  const view = query.data;
  const lotSize = view?.lot_size ?? 75;

  // -- client re-derivation -------------------------------------------------
  const strikes = useMemo(() => (view ? view.strikes.map((r) => r.strike) : []), [view]);
  const step = useMemo(() => inferStep(strikes), [strikes]);

  const series = useMemo(() => view?.series ?? [], [view]);
  const hasSeries = series.length >= 2;
  // Two frames is enough to drag — the window still collapses and the chart
  // still redraws. Below that there is genuinely nothing to move between.
  const canScrub = series.length >= 2;
  const lastIdx = Math.max(0, series.length - 1);
  const ticks = useMemo(() => axisTicks(series), [series]);
  const nowIdx = nowFrameIdx < 0 ? lastIdx : Math.min(nowFrameIdx, lastIdx);
  const openIdx = Math.min(openFrameIdx < 0 ? 0 : Math.min(openFrameIdx, lastIdx), nowIdx);

  const nowFrame = hasSeries ? series[nowIdx] : undefined;
  const openFrame = hasSeries ? series[openIdx] : undefined;

  // Anchors for everything the chart draws. All three follow the frame being
  // shown so that scrubbing back to 10:30 recentres the strike window, the spot
  // line and the max-pain marker on 10:30's market — not on the newest one.
  const spotNow = nowFrame?.spot ?? view?.spot ?? 0;
  const atmNow = nowFrame?.atm ?? view?.atm_strike ?? 0;
  const maxPainNow = nowFrame?.max_pain ?? view?.max_pain ?? 0;

  /**
   * The strikes the chart draws, centred on the shown frame's ATM.
   *
   * Centring on the payload's ATM instead was the bug behind "the chart looks
   * wrong": spot had moved during the session, so the window sat off to one
   * side of the OI peak and the profile read as a monotonic decay with the spot
   * line pinned to the far edge.
   */
  const visible = useMemo(
    () => withinWindow(strikes, atmNow, step, strikeFilter === 'all' ? 0 : strikeFilter),
    [strikes, atmNow, step, strikeFilter]
  );

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

  /**
   * What, if anything, to say about the data behind the timeline.
   *
   * Says nothing once a real session has accumulated — a caption that qualifies
   * every reading trains people to ignore it. On `live_proxy` there is no
   * recorded open at all: the previous copy claimed both end points "have been
   * recorded", which was never true on that tier.
   */
  const qualityNote =
    view?.data_quality === 'live_proxy'
      ? 'Live estimate — the open is inferred from day-over-day OI change, not from a recorded snapshot.'
      : view?.open_is_estimated && series.length > 1
        ? `The ${timeLabel(series[0]!.t)} baseline is derived from the day’s OI change; recorded history starts at ${timeLabel(series[1]!.t)}.`
        : series.length > 0 && series.length < 3
          ? `Only ${series.length} snapshot${series.length === 1 ? '' : 's'} recorded so far today, so the timeline is coarse — it fills in through market hours.`
          : '';

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
  // Ticks once a second, which also re-renders the freshness label below for
  // free — it needs no state of its own.
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);

  const updatedAt = query.dataUpdatedAt;
  const isStale = Boolean(updatedAt) && now - updatedAt > STALE_AFTER_MS;

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
                  <span className={cx(s.live, isStale && s.stale)}>
                    <span className={cx(s.dot, query.isFetching && s.pulse)} />
                    <span>
                      {dateLabel(now)}, {clockLabel(now)} IST
                    </span>
                    <span className={s.sep} aria-hidden="true">
                      ·
                    </span>
                    <span>{REFETCH_MS / 1000}s</span>
                    <span className={s.sep} aria-hidden="true">
                      ·
                    </span>
                    {/* Not decoration: with nothing writing snapshots the page
                        polls happily and gets identical bytes forever, so this
                        is the only thing that tells a quiet feed from a dead
                        one. */}
                    <span>updated {freshnessLabel(updatedAt, now)}</span>
                  </span>
                </div>
              </div>

              <OpenInterestChart
                bars={bars}
                mode={mode}
                // From the frame being shown, so the spot line and max-pain
                // marker travel with the bars when the timeline is scrubbed.
                spot={spotNow}
                maxPain={maxPainNow}
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
                {/* Rendered unconditionally: moving only the right handle is the
                    literal "show me 10:30" gesture, and getting back to live has
                    to be one obvious click away from wherever you left it. */}
                <button
                  type="button"
                  className={s.reset}
                  onClick={resetSlider}
                  disabled={!canScrub}
                >
                  Reset
                </button>
                <span className={s.end}>
                  <span className={s.endCaption}>Baseline</span>
                  {openLabel}
                </span>
                <TimeRangeSlider
                  min={0}
                  max={lastIdx}
                  openIndex={openIdx}
                  nowIndex={nowIdx}
                  disabled={!canScrub}
                  openLabel={openLabel}
                  nowLabel={nowLabel}
                  ticks={ticks}
                  onOpenChange={onOpenHandleChange}
                  onNowChange={onNowHandleChange}
                />
                <span className={s.end}>
                  <span className={s.endCaption}>As of</span>
                  {nowLabel}
                </span>
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
                window. {qualityNote}
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
