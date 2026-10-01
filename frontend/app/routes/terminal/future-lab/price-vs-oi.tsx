import { useQuery } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';
import { useInstruments } from '$contexts/instrument-catalog/queries';
import EChart from '$shared/charts/EChart';
import { buildPriceVsOiOption } from '$shared/charts/options/price-vs-oi';
import { useChartTheme } from '$shared/charts/theme/use-chart-theme';
import { isoDateIST, lastTradingDayIST } from '$shared/formatting/ist-clock';
import DataSourceBadge from '$shared/ui/DataSourceBadge';
import DatePicker from '$shared/ui/DatePicker';
import Select from '$shared/ui/Select';
import { cx } from '$shared/ui/cx';
import IconChart from '$shared/ui/icons/IconChart';
import IconChevronDown from '$shared/ui/icons/IconChevronDown';
import { ReplayToggle, SessionStatus } from './components/SessionHeader';
import {
  clampCursor,
  DEFAULT_INTERVAL,
  expiryLabel,
  feedAgeLabel,
  feedAgeMs,
  filterInstruments,
  fmtOi,
  fmtPrice,
  getPriceOiSeries,
  OI_LABEL,
  REFETCH_MS,
  sliceTo,
  timeLabel,
  toPickerEntries,
  type Interval,
  type PriceOiView
} from './price-vs-oi-data';
import s from './price-vs-oi.module.css';
import type { Route } from './+types/price-vs-oi';

export const meta: Route.MetaFunction = () => [
  { title: 'Price vs OI · Future Lab · MarketCompass' }
];

type Mode = 'live' | 'historical';

/** Matches the query's own poll, so the ring counts down to a real refresh. */
const REFRESH_SECONDS = REFETCH_MS / 1000;

/** Frames per second of replay. Fast enough to read a session in a minute. */
const REPLAY_FPS = 12;

const INTERVALS: readonly { value: Interval; label: string }[] = [
  { value: '1m', label: '1m' },
  { value: '5m', label: '5m' },
  { value: '15m', label: '15m' },
  { value: '1h', label: '1h' }
];

export default function FuturePriceVsOi() {
  const [symbol, setSymbol] = useState('NIFTY');
  const [search, setSearch] = useState('');
  const [mode, setMode] = useState<Mode>('live');
  const [date, setDate] = useState(lastTradingDayIST);
  const [interval, setInterval] = useState<Interval>(DEFAULT_INTERVAL);
  const [showPrice, setShowPrice] = useState(true);
  const [showOi, setShowOi] = useState(true);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  // `null` means "not replaying" — the chart shows the whole session.
  const [cursor, setCursor] = useState<number | null>(null);
  const [playing, setPlaying] = useState(false);

  const { instruments } = useInstruments();
  const entries = useMemo(() => toPickerEntries(instruments), [instruments]);
  const visibleEntries = useMemo(() => filterInstruments(entries, search), [entries, search]);
  const current = entries.find((entry) => entry.symbol === symbol);

  const historicalDate = mode === 'historical' ? date : undefined;

  const query = useQuery<PriceOiView>({
    queryKey: ['future-lab', 'price-oi', symbol, interval, mode, historicalDate],
    queryFn: () =>
      getPriceOiSeries(symbol, {
        interval,
        ...(historicalDate ? { date: historicalDate } : {})
      }),
    // A replay would jump under the reader's feet if the series reloaded mid-run.
    refetchInterval: mode === 'live' && cursor === null ? REFETCH_MS : false
  });

  const view = query.data;
  const theme = useChartTheme();
  const frames = view?.t.length ?? 0;

  // Changing what is drawn ends the replay: a cursor into the old series means
  // nothing in the new one, and silently re-pointing it would be worse.
  useEffect(() => {
    setCursor(null);
    setPlaying(false);
  }, [symbol, interval, mode, historicalDate]);

  useEffect(() => {
    if (!playing || frames === 0) return;
    const timer = window.setInterval(() => {
      setCursor((prev) => {
        const next = (prev ?? 0) + 1;
        if (next >= frames - 1) {
          setPlaying(false);
          return frames - 1;
        }
        return next;
      });
    }, 1000 / REPLAY_FPS);
    return () => window.clearInterval(timer);
  }, [playing, frames]);

  const option = useMemo(() => {
    if (!view) return null;
    return buildPriceVsOiOption(
      {
        timestamps: sliceTo(view.t, cursor),
        price: sliceTo(view.price, cursor),
        oi: sliceTo(view.oi, cursor),
        formatPrice: fmtPrice,
        formatOi: (value: number) => fmtOi(value),
        oiName: OI_LABEL,
        showPrice,
        showOi
      },
      theme
    );
  }, [view, cursor, showPrice, showOi, theme]);

  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  // Feed-age only matters for the live tape; a replayed past day is never "stale".
  const feedAge = mode === 'live' && cursor === null ? feedAgeMs(view?.now_ts, now) : null;

  function step(delta: number) {
    const index = visibleEntries.findIndex((entry) => entry.symbol === symbol);
    const pool = visibleEntries.length > 0 ? visibleEntries : entries;
    if (pool.length === 0) return;
    const from = index === -1 ? 0 : index;
    const next = pool[(from + delta + pool.length) % pool.length];
    if (next) setSymbol(next.symbol);
  }

  function toggleReplay() {
    if (frames < 2) return;
    if (cursor === null) {
      setCursor(0);
      setPlaying(true);
      return;
    }
    setCursor(null);
    setPlaying(false);
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
                  <span className={s.badge}>{current?.badge ?? '··'}</span>
                  <span className={s.short} title={current?.name ?? symbol}>
                    {symbol}
                  </span>
                  <span className={s.cyclers}>
                    <button type="button" aria-label="Previous" onClick={() => step(-1)}>
                      ‹
                    </button>
                    <button type="button" aria-label="Next" onClick={() => step(1)}>
                      ›
                    </button>
                  </span>
                </div>

                {/* A cycler alone is unusable across 219 contracts, so the list
                    is searchable and the arrows step within what it shows. */}
                <input
                  className={s.search}
                  type="search"
                  value={search}
                  placeholder="Search symbol…"
                  aria-label="Search instruments"
                  onChange={(event) => setSearch(event.currentTarget.value)}
                />
                <ul className={s.pickList}>
                  {visibleEntries.map((entry) => (
                    <li key={entry.symbol}>
                      <button
                        type="button"
                        className={cx(s.pickRow, entry.symbol === symbol && s.pickOn)}
                        onClick={() => setSymbol(entry.symbol)}
                      >
                        <span className={s.pickSym}>{entry.symbol}</span>
                        <span className={s.pickName}>{entry.name}</span>
                      </button>
                    </li>
                  ))}
                  {visibleEntries.length === 0 ? (
                    <li className={s.pickEmpty}>No contract matches that.</li>
                  ) : null}
                </ul>

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
                    {/* Read-only here, unlike the board pages, and for a
                        real reason: this chart is drawn from the archived
                        session the capture worker writes, and it captures the
                        front month only. Offering a back month would promise
                        an intraday series that does not exist. */}
                    <div className={s.select}>
                      <span>{expiryLabel(view.expiry_date)}</span>
                      <span className={s.caret} aria-hidden="true">
                        <IconChevronDown />
                      </span>
                    </div>
                  </div>
                  <div>
                    <p className={s.subLabel}>Time</p>
                    <Select
                      className={s.selectNative}
                      ariaLabel="Time interval"
                      value={interval}
                      onChange={setInterval}
                      options={INTERVALS.map((option) => ({
                        value: option.value,
                        label: option.label
                      }))}
                    />
                  </div>
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

          {/* RIGHT MAIN */}
          <div className={s.main}>
            <div className={s.topBar}>
              <h1 className={s.title}>
                <span className={s.ico} aria-hidden="true">
                  <IconChart />
                </span>
                Future Price vs OI
              </h1>
              <div className={s.headerRight}>
                <ReplayToggle
                  on={cursor !== null}
                  onToggle={toggleReplay}
                  disabled={frames < 2}
                  reason={
                    frames < 2 ? 'Replay needs a captured session to walk through.' : undefined
                  }
                />
                {/* The hand-rolled strip this page used to carry is now the
                    shared one; `feedAge` stays beside it because it is a
                    different fact — how far the *broker's* feed is behind,
                    not how old our copy of it is. */}
                <SessionStatus
                  intervalSeconds={REFRESH_SECONDS}
                  active={mode === 'live' && cursor === null}
                  updatedAt={query.dataUpdatedAt}
                  {...(mode === 'live' ? {} : { label: `Archived · ${date}` })}
                />
                {feedAge !== null ? (
                  <span className={cx(s.live, s.stale)}>{feedAgeLabel(feedAge)}</span>
                ) : null}
                <DataSourceBadge source={view.source} />
              </div>
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
                  {OI_LABEL}
                </button>
              </div>

              {view.t.length === 0 || option === null ? (
                <p className={s.empty}>
                  {mode === 'historical'
                    ? 'No session archived for that date.'
                    : 'Nothing captured for today yet — the series fills in as the board capture records it.'}
                </p>
              ) : (
                <EChart option={option} className={s.chart} />
              )}
            </section>

            {cursor !== null ? (
              <ReplayBar
                cursor={clampCursor(cursor, frames)}
                frames={frames}
                playing={playing}
                at={view.t[clampCursor(cursor, frames)]}
                onPlay={() => setPlaying((on) => !on)}
                onSeek={setCursor}
                onExit={() => {
                  setCursor(null);
                  setPlaying(false);
                }}
              />
            ) : null}

            <p className={s.caption}>{captionFor(view)}</p>
          </div>
        </div>
      ) : null}
    </div>
  );
}

/**
 * The replay scrubber.
 *
 * Drives a cursor over the frames already fetched — the whole session arrives
 * in one payload, so winding back and forth costs no request and cannot show a
 * frame the archive does not hold.
 */
function ReplayBar({
  cursor,
  frames,
  playing,
  at,
  onPlay,
  onSeek,
  onExit
}: {
  cursor: number;
  frames: number;
  playing: boolean;
  at: string | undefined;
  onPlay: () => void;
  onSeek: (next: number) => void;
  onExit: () => void;
}) {
  return (
    <div className={s.replayBar}>
      <button
        type="button"
        className={s.playBtn}
        onClick={onPlay}
        aria-label={playing ? 'Pause replay' : 'Play replay'}
      >
        {playing ? '❚❚' : '▶'}
      </button>
      <input
        className={s.scrub}
        type="range"
        min={0}
        max={Math.max(frames - 1, 0)}
        value={cursor}
        aria-label="Replay position"
        onChange={(event) => onSeek(Number(event.currentTarget.value))}
      />
      <span className={s.replayAt}>
        {at ? timeLabel(at) : '—'}
        <span className={s.replayCount}>
          {cursor + 1}/{frames}
        </span>
      </span>
      <button type="button" className={s.exitReplay} onClick={onExit}>
        Exit
      </button>
    </div>
  );
}

/** The plain-English note under the chart, from the data tier. */
function captionFor(view: PriceOiView): string {
  const oi = `${OI_LABEL} is this contract’s own open interest, not the option chain’s.`;
  if (view.data_quality === 'empty') {
    return `Nothing captured yet — the series fills in as the board capture records it. ${oi}`;
  }
  if (view.data_quality === 'live_proxy') {
    return `Nothing archived for this day — showing the previous close against the live board. The shape fills in as frames are captured. ${oi}`;
  }
  const first = view.t[0];
  const gaps = view.oi.filter((value) => value === null).length;
  const note = gaps
    ? ` ${gaps} frame${gaps === 1 ? '' : 's'} fell between open-interest sweeps and show a gap.`
    : '';
  return first ? `Recorded from ${timeLabel(first)} at ${view.interval} buckets. ${oi}${note}` : oi;
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
