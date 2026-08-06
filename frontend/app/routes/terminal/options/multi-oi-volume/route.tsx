import { useQuery } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';
import { seriesColor, type SeriesLine } from '$shared/charts/options/multi-series';
import { cx } from '$shared/ui/cx';
import IconChart from '$shared/ui/icons/IconChart';
import IconChevronDown from '$shared/ui/icons/IconChevronDown';
import ContractPicker from './components/ContractPicker';
import SeriesChart from './components/SeriesChart';
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

export default function MultiOiVolume() {
  const [instIdx, setInstIdx] = useState(0);
  const [interval, setInterval] = useState<Interval>(DEFAULT_INTERVAL);
  const [topN, setTopN] = useState(5);
  const [showNet, setShowNet] = useState(false);
  /** Explicit picks, or `null` while the top-N defaults are in charge. */
  const [customOi, setCustomOi] = useState<string[] | null>(null);
  const [picking, setPicking] = useState(false);

  const instrument = INSTRUMENTS[instIdx] ?? INSTRUMENTS[0]!;

  function cycle(delta: number) {
    setInstIdx((current) => (current + delta + INSTRUMENTS.length) % INSTRUMENTS.length);
    // A strike that exists on NIFTY means nothing on BANKNIFTY, so an explicit
    // selection cannot survive an instrument change.
    setCustomOi(null);
  }

  const query = useQuery<OiSeriesView>({
    queryKey: ['options-lab', 'oi-series', instrument.symbol, interval],
    queryFn: () => getOiSeries(instrument.symbol, interval),
    refetchInterval: REFETCH_MS
  });

  const view = query.data;
  const contracts = useMemo(() => view?.contracts ?? [], [view]);
  const byId = useMemo(
    () => new Map(contracts.map((contract) => [contract.id, contract])),
    [contracts]
  );

  // -- selection ------------------------------------------------------------
  const oiIds = useMemo(
    () => customOi ?? topByLatest(contracts, 'oi', topN),
    [customOi, contracts, topN]
  );

  const oiPicked = useMemo(() => resolve(oiIds, byId), [oiIds, byId]);

  const times = useMemo(() => (view?.t ?? []).map(timeLabel), [view]);
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

              <PickerRow
                title="Contracts"
                count={topN}
                onCount={(n) => {
                  setTopN(n);
                  setCustomOi(null);
                }}
                picked={oiPicked}
                custom={customOi !== null}
                onSelect={() => setPicking(true)}
                onReset={() => setCustomOi(null)}
              />

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
              <span className={s.live}>
                <span className={cx(s.dot, query.isFetching && s.pulse)} />
                {clock} IST
              </span>
            </div>

            <SeriesChart
              title="MultiStrike OI"
              icon={<IconChart />}
              lines={oiLines}
              times={times}
              futures={futures}
              formatValue={formatValue}
              formatPrice={fmtPrice}
              group={CHART_GROUP}
            />
            <SeriesChart
              title="MultiStrike OI Change"
              icon={<IconChart />}
              lines={changeLines}
              times={times}
              futures={futures}
              formatValue={formatValue}
              formatPrice={fmtPrice}
              group={CHART_GROUP}
            />

            <p className={s.caption}>
              {view.data_quality === 'empty'
                ? 'No snapshots recorded for today yet — the series fills in as the ingest worker captures them.'
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
            setCustomOi(ids);
            setPicking(false);
          }}
          onClose={() => setPicking(false)}
        />
      ) : null}
    </div>
  );
}

/** One sidebar picker: a top-N count, the coloured chips, and a Select button. */
function PickerRow({
  title,
  count,
  onCount,
  picked,
  custom,
  onSelect,
  onReset
}: {
  title: string;
  count: number;
  onCount: (n: number) => void;
  picked: ContractSeries[];
  custom: boolean;
  onSelect: () => void;
  onReset: () => void;
}) {
  return (
    <div className={s.picker}>
      <div className={s.pickerHead}>
        <span className={s.pickerTitle}>{title}</span>
        {custom ? (
          <button type="button" className={s.link} onClick={onReset}>
            Reset
          </button>
        ) : (
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
        )}
        <button type="button" className={s.link} onClick={onSelect}>
          Select
        </button>
      </div>
      <div className={s.chips}>
        {picked.map((contract, index) => (
          <span key={contract.id} className={s.chip}>
            <i className={s.swatch} style={{ background: seriesColor(index) }} />
            {contractLabel(contract)}
          </span>
        ))}
        {picked.length === 0 ? <span className={s.chipEmpty}>Nothing to plot yet</span> : null}
      </div>
    </div>
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
