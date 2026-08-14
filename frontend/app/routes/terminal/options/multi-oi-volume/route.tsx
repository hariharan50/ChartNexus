import { useQuery } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';
import { seriesColor, type SeriesLine } from '$shared/charts/options/multi-series';
import { cx } from '$shared/ui/cx';
import IconChart from '$shared/ui/icons/IconChart';
import IconChevronDown from '$shared/ui/icons/IconChevronDown';
import { lastTradingDayIST } from '$shared/formatting/ist-clock';
import ContractPicker from './components/ContractPicker';
import HistoryMode, { type Mode } from '../components/HistoryMode';
import SeriesChart from '../components/SeriesChart';
import { feedAgeLabel, feedAgeMs } from '../open-interest/oi-data';
import {
  contractLabel,
  DEFAULT_INTERVAL,
  expiryLabel,
  fmtOi,
  fmtPrice,
  getOiSeries,
  INTERVALS,
  metricValues,
  peMinusCe,
  REFETCH_MS,
  timeLabel,
  topByLatest,
  TOP_N_CHOICES,
  type ContractSeries,
  type Interval,
  type Metric,
  type OiSeriesView
} from './multi-oi-data';
import s from './route.module.css';
import type { Route } from './+types/route';

export const meta: Route.MetaFunction = () => [{ title: 'Multi OI & Volume · Options Lab' }];

const INSTRUMENTS = [
  { short: 'NIFTY', badge: '50', symbol: 'NIFTY' },
  { short: 'SENSEX', badge: 'BSE', symbol: 'SENSEX' },
  { short: 'BANKNIFTY', badge: 'BNK', symbol: 'BANKNIFTY' }
];

/** Charts sharing this group share one crosshair. */
const CHART_GROUP = 'multi-oi';

type StrikeSourceId = 'volume' | 'oi' | 'custom';

/** Order matters — this is the sidebar's reading order. */
const SOURCES: { id: StrikeSourceId; title: string; hint: string }[] = [
  { id: 'volume', title: 'High Volume', hint: 'No volume recorded yet' },
  { id: 'oi', title: 'High OI', hint: 'No open interest recorded yet' },
  { id: 'custom', title: 'Custom Strikes', hint: 'Nothing picked yet — press Edit' }
];

export default function MultiOiVolume() {
  const [instIdx, setInstIdx] = useState(0);
  const [mode, setMode] = useState<Mode>('live');
  const [date, setDate] = useState(lastTradingDayIST);
  const [interval, setInterval] = useState<Interval>(DEFAULT_INTERVAL);
  const [topN, setTopN] = useState(5);
  const [showNet, setShowNet] = useState(false);
  /**
   * Where the plotted strikes come from. Exactly one source is live at a time —
   * three independent selections feeding one pair of charts would leave no way
   * to tell which set you were looking at.
   */
  const [source, setSource] = useState<StrikeSourceId>('oi');
  const [customIds, setCustomIds] = useState<string[]>([]);
  const [picking, setPicking] = useState(false);

  const instrument = INSTRUMENTS[instIdx] ?? INSTRUMENTS[0]!;

  function cycle(delta: number) {
    setInstIdx((current) => (current + delta + INSTRUMENTS.length) % INSTRUMENTS.length);
    // A strike that exists on NIFTY means nothing on BANKNIFTY, so an explicit
    // selection cannot survive an instrument change.
    setCustomIds([]);
    if (source === 'custom') setSource('oi');
  }

  const historyDate = mode === 'historical' ? date : undefined;
  const query = useQuery<OiSeriesView>({
    queryKey: ['options-lab', 'oi-series', instrument.symbol, interval, mode, historyDate],
    queryFn: () => getOiSeries(instrument.symbol, interval, { date: historyDate }),
    refetchInterval: mode === 'live' ? REFETCH_MS : false
  });

  const view = query.data;
  const contracts = useMemo(() => view?.contracts ?? [], [view]);
  const byId = useMemo(
    () => new Map(contracts.map((contract) => [contract.id, contract])),
    [contracts]
  );

  // -- selection ------------------------------------------------------------
  const oiIds = useMemo(() => {
    if (source === 'custom') return customIds;
    return topByLatest(contracts, source === 'volume' ? 'volume' : 'oi', topN);
  }, [source, customIds, contracts, topN]);

  const oiPicked = useMemo(() => resolve(oiIds, byId), [oiIds, byId]);

  // Raw ISO, not display strings: the chart derives its own axis labels from
  // the instants.
  const times = view?.t ?? [];
  const futures = view?.fut ?? [];
  const lotSize = view?.lot_size ?? 75;

  const oiLines = useMemo(() => toLines(oiPicked, 'oi'), [oiPicked]);
  const changeLines = useMemo(() => {
    const lines = toLines(oiPicked, 'change');
    if (!showNet || oiPicked.length === 0) return lines;
    return [
      ...lines,
      {
        id: 'pe-ce',
        label: 'PE−CE OI Change',
        color: seriesColor(oiPicked.length),
        values: peMinusCe(oiPicked)
      }
    ];
  }, [oiPicked, showNet]);

  const formatValue = useMemo(() => (value: number) => fmtOi(value, false, lotSize), [lotSize]);

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

  // How far the drawn series lags the clock beside it. `null` when current, and
  // outside trading hours — see `feedAgeMs`.
  const feedAge = feedAgeMs(view?.now_ts, now);

  return (
    <div className={s.page}>
      {query.isError ? (
        <div className={s.banner} role="alert">
          <span>Couldn’t load the OI series.</span>
          <button type="button" onClick={() => void query.refetch()}>
            Retry
          </button>
        </div>
      ) : !view && query.isPending ? (
        <div className={cx(s.panel, s.muted)}>Loading Multi OI &amp; Volume…</div>
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

              <HistoryMode mode={mode} date={date} onMode={setMode} onDate={setDate} />

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
                  {/* Labelled on the control itself. A visually-hidden <span>
                      would depend on a global utility class, which a CSS module
                      cannot see — the first version rendered the label text. */}
                  <select
                    className={s.selectNative}
                    aria-label="Time interval"
                    value={interval}
                    onChange={(e) => setInterval(e.currentTarget.value as Interval)}
                  >
                    {INTERVALS.map((option) => (
                      <option key={option.value} value={option.value} disabled={option.disabled}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <p className={s.subLabel}>Strike selection</p>
              {SOURCES.map((entry) => (
                <StrikeSource
                  key={entry.id}
                  title={entry.title}
                  hint={entry.hint}
                  active={source === entry.id}
                  countable={entry.id !== 'custom'}
                  count={topN}
                  onCount={setTopN}
                  picked={source === entry.id ? oiPicked : []}
                  onActivate={() => {
                    // Custom Strikes only goes live on Apply. Switching on the
                    // way *into* the picker would empty the charts behind the
                    // modal and leave them empty if you then cancelled.
                    if (entry.id === 'custom') setPicking(true);
                    else setSource(entry.id);
                  }}
                  onEdit={() => setPicking(true)}
                />
              ))}

              <label className={s.netToggle}>
                <input
                  type="checkbox"
                  checked={showNet}
                  onChange={(e) => setShowNet(e.currentTarget.checked)}
                />
                <span>Show PE−CE net change</span>
              </label>
            </section>
          </aside>

          {/* RIGHT MAIN */}
          <div className={s.main}>
            <div className={s.topBar}>
              <span className={s.meta}>
                ATM {view.atm_strike} · {view.contracts.length} contracts · {view.interval} buckets
              </span>
              <span className={cx(s.live, feedAge !== null && s.stale)}>
                <span className={cx(s.dot, query.isFetching && s.pulse)} />
                {clock} IST
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

            <SeriesChart
              title="MultiStrike OI"
              subtitle="Total open interest held on each contract through the session."
              icon={<IconChart />}
              valueAxisName="Open interest"
              lines={oiLines}
              timestamps={times}
              futures={futures}
              formatValue={formatValue}
              formatPrice={fmtPrice}
              group={CHART_GROUP}
            />
            <SeriesChart
              title="MultiStrike OI Change"
              subtitle="Positions added or closed since the 9:15 open — where today's flow went."
              icon={<IconChart />}
              valueAxisName="OI change"
              lines={changeLines}
              timestamps={times}
              futures={futures}
              formatValue={formatValue}
              formatPrice={fmtPrice}
              group={CHART_GROUP}
            />

            <p className={s.caption}>
              {view.data_quality === 'empty'
                ? mode === 'historical'
                  ? 'No session archived for that date.'
                  : 'No snapshots recorded for today yet — the series fills in as the ingest worker captures them.'
                : view.data_quality === 'live_proxy'
                  ? 'Nothing archived for today yet — showing the 9:15 open against the live chain. The shape fills in as the ingest worker captures snapshots.'
                  : view.open_is_estimated
                    ? `The ${timeLabel(view.t[0]!)} baseline is derived from the day’s OI change; recorded history starts at ${timeLabel(view.t[1] ?? view.t[0]!)}.`
                    : `Recorded from ${timeLabel(view.t[0]!)} at ${view.interval} buckets.`}
            </p>
          </div>
        </div>
      ) : null}

      {picking ? (
        <ContractPicker
          contracts={contracts}
          selected={oiIds}
          title="Choose contracts"
          onApply={(ids) => {
            setCustomIds(ids);
            setSource('custom');
            setPicking(false);
          }}
          onClose={() => setPicking(false)}
        />
      ) : null}
    </div>
  );
}

/**
 * One way of choosing which strikes the charts plot.
 *
 * Only the live source shows its chips; the others collapse to a Select button.
 * Three expanded lists of five strikes would fill the sidebar with contracts
 * that are not on the chart, and nothing on screen would say which set was.
 */
function StrikeSource({
  title,
  hint,
  active,
  countable,
  count,
  onCount,
  picked,
  onActivate,
  onEdit
}: {
  title: string;
  hint: string;
  active: boolean;
  countable: boolean;
  count: number;
  onCount: (n: number) => void;
  picked: ContractSeries[];
  onActivate: () => void;
  onEdit: () => void;
}) {
  return (
    /* Named so it is a labelled group rather than an anonymous box: three
       stacked sections of controls are exactly what a landmark name is for. */
    <section className={cx(s.source, active && s.sourceActive)} aria-label={title}>
      <div className={s.sourceHead}>
        <span className={s.sourceTitle}>{title}</span>
        {active && countable ? (
          <select
            className={s.selectNative}
            aria-label={`${title} count`}
            value={count}
            onChange={(e) => onCount(Number(e.currentTarget.value))}
          >
            {TOP_N_CHOICES.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        ) : null}
        {active && !countable ? (
          <button type="button" className={s.link} onClick={onEdit}>
            Edit
          </button>
        ) : null}
        {!active ? (
          <button type="button" className={s.link} onClick={onActivate}>
            Select
          </button>
        ) : null}
      </div>

      {active ? (
        <div className={s.chips}>
          {picked.map((contract, index) => (
            <span key={contract.id} className={s.chip}>
              <i className={s.swatch} style={{ background: seriesColor(index) }} />
              {contractLabel(contract)}
            </span>
          ))}
          {picked.length === 0 ? <span className={s.chipEmpty}>{hint}</span> : null}
        </div>
      ) : null}
    </section>
  );
}

function resolve(ids: string[], byId: Map<string, ContractSeries>): ContractSeries[] {
  return ids
    .map((id) => byId.get(id))
    .filter((contract): contract is ContractSeries => contract !== undefined);
}

function toLines(picked: ContractSeries[], metric: Metric): SeriesLine[] {
  return picked.map((contract, index) => ({
    id: contract.id,
    label: contractLabel(contract),
    color: seriesColor(index),
    values: metricValues(contract, metric)
  }));
}
