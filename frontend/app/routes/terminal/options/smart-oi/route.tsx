import { useQuery } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';
import { getExpiries } from '$contexts/broker-connections/api';
import type { SeriesLine } from '$shared/charts/options/multi-series';
import { lastTradingDayIST } from '$shared/formatting/ist-clock';
import { cx } from '$shared/ui/cx';
import IconChart from '$shared/ui/icons/IconChart';
import IconFx from '$shared/ui/icons/IconFx';
import type { Mode } from '../components/HistoryMode';
import SeriesChart from '../components/SeriesChart';
import PricePanel from './components/PricePanel';
import ReplayBar, { REPLAY_SPEEDS, type ReplaySpeed } from './components/ReplayBar';
import SmartOiToolbar from './components/SmartOiToolbar';
import {
  CALL_COLOR,
  DEFAULT_INTERVAL,
  DEFAULT_SPAN,
  OI_INSTRUMENTS,
  PUT_COLOR,
  REFETCH_MS,
  STALE_AFTER_MS,
  csvFilename,
  fmtOi,
  fmtPrice,
  fmtRatio,
  frameHeadFor,
  getSmartOi,
  smartOiCsv,
  type Interval,
  type RangeMode,
  type SmartOiView,
  type StrikeMode
} from './smart-oi-data';
import s from './route.module.css';
import type { Route } from './+types/route';

export const meta: Route.MetaFunction = () => [{ title: 'Smart OI · Options Lab' }];

/** Purple for the PE−CE spread, matching the reference and the Vega page. */
const SPREAD_COLOR = '#a855f7';
/** Blue and amber for the two ratios, which are not sides and must not read as one. */
const OI_PCR_COLOR = '#3b82f6';
const VOL_PCR_COLOR = '#eab308';

/** Both right-hand charts share a crosshair. */
const CHART_GROUP = 'smart-oi';

const NO_BARS: SmartOiView['bars'] = [];
const NO_TIMES: string[] = [];
const NO_VALUES: (number | null)[] = [];

export default function SmartOi() {
  const [instIdx, setInstIdx] = useState(0);
  const [dataMode, setDataMode] = useState<Mode>('live');
  const [date, setDate] = useState(lastTradingDayIST);
  const [interval, setIntervalChoice] = useState<Interval>(DEFAULT_INTERVAL);
  const [expiry, setExpiry] = useState<string | undefined>(undefined);

  const [rangeMode, setRangeMode] = useState<RangeMode>('range');
  const [strikeMode, setStrikeMode] = useState<StrikeMode>('auto');
  const [span, setSpan] = useState<number | null>(DEFAULT_SPAN);
  const [custom, setCustom] = useState({ low: '', high: '' });

  const [replay, setReplay] = useState(false);
  const [head, setHead] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState<ReplaySpeed>(REPLAY_SPEEDS[1]);

  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, []);

  const instrument = OI_INSTRUMENTS[instIdx] ?? OI_INSTRUMENTS[0]!;
  const historyDate = dataMode === 'historical' ? date : undefined;

  // Custom bounds only reach the request once both ends parse. A half-typed
  // "24" would otherwise fire a query for a one-strike window on every keystroke.
  const bounds = useMemo(() => {
    if (rangeMode !== 'custom') return { low: undefined, high: undefined };
    const low = Number(custom.low);
    const high = Number(custom.high);
    if (!custom.low || !custom.high || Number.isNaN(low) || Number.isNaN(high) || low >= high) {
      return { low: undefined, high: undefined };
    }
    return { low, high };
  }, [rangeMode, custom]);

  const query = useQuery<SmartOiView>({
    queryKey: [
      'options-lab',
      'smart-oi',
      instrument.symbol,
      interval,
      strikeMode,
      span,
      bounds.low,
      bounds.high,
      expiry,
      dataMode,
      historyDate
    ],
    queryFn: () =>
      getSmartOi(instrument.symbol, {
        interval,
        mode: strikeMode,
        span,
        minStrike: bounds.low,
        maxStrike: bounds.high,
        expiry,
        date: historyDate
      }),
    // Replay is a reading of a fixed session; a poll underneath it would move
    // the sweep's own ground while the reader is stepping through it.
    refetchInterval: dataMode === 'live' && !replay ? REFETCH_MS : false
  });

  const expiryQuery = useQuery({
    queryKey: ['market', 'expiries', instrument.symbol],
    queryFn: () => getExpiries(instrument.symbol),
    staleTime: 60 * 60_000
  });

  const view = query.data;
  // Stable empty arrays, not fresh literals: a new `[]` every render would
  // re-run every downstream `useMemo` on every tick of the one-second clock.
  const bars = view?.bars ?? NO_BARS;
  const times = view?.t ?? NO_TIMES;

  // Entering replay parks the head on the newest bar, so the first thing on
  // screen is the chart the reader was already looking at.
  useEffect(() => {
    if (replay) setHead(Math.max(0, bars.length - 1));
    else setPlaying(false);
    // Only on the toggle: re-parking on every refetch would fight the sweep.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [replay]);

  useEffect(() => {
    if (!replay || !playing) return;
    const id = window.setInterval(() => {
      setHead((current) => {
        if (current >= bars.length - 1) {
          setPlaying(false);
          return current;
        }
        return current + 1;
      });
    }, 1000 / speed);
    return () => window.clearInterval(id);
  }, [replay, playing, speed, bars.length]);

  // The bar axis and the frame axis have different cadences, so the head
  // crosses between them by timestamp rather than by index.
  const frameHead = useMemo(
    () => (replay ? frameHeadFor(times, bars, head) : undefined),
    [replay, times, bars, head]
  );

  const shown = useMemo(() => {
    if (!replay || !view) {
      return {
        bars,
        smartOi: view?.smart_oi ?? NO_VALUES,
        call: view?.call_vol ?? NO_VALUES,
        put: view?.put_vol ?? NO_VALUES
      };
    }
    const upto = head + 1;
    return {
      bars: view.bars.slice(0, upto),
      smartOi: view.smart_oi.slice(0, upto),
      call: view.call_vol.slice(0, upto),
      put: view.put_vol.slice(0, upto)
    };
  }, [replay, view, bars, head]);

  const oiLines = useMemo<SeriesLine[]>(() => {
    if (!view) return [];
    return [
      { id: 'put', label: 'Put OI (Chg Day)', color: PUT_COLOR, values: view.put_oi_chg },
      { id: 'call', label: 'Call OI (Chg Day)', color: CALL_COLOR, values: view.call_oi_chg },
      { id: 'spread', label: 'PE-CE (Chg Day)', color: SPREAD_COLOR, values: view.pe_ce_chg }
    ];
  }, [view]);

  const pcrLines = useMemo<SeriesLine[]>(() => {
    if (!view) return [];
    return [
      { id: 'oi-pcr', label: 'OI PCR', color: OI_PCR_COLOR, values: view.oi_pcr },
      { id: 'vol-pcr', label: 'Vol PCR (Total)', color: VOL_PCR_COLOR, values: view.vol_pcr }
    ];
  }, [view]);

  function cycle(step: number) {
    setInstIdx((current) => (current + step + OI_INSTRUMENTS.length) % OI_INSTRUMENTS.length);
  }

  function download() {
    if (!view) return;
    const blob = new Blob([smartOiCsv(view)], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = csvFilename(view.symbol, view.interval);
    link.click();
    URL.revokeObjectURL(url);
  }

  if (query.isError) {
    return (
      <div className={s.page}>
        <div className={s.banner} role="alert">
          <span>Smart OI could not load. {(query.error as Error).message}</span>
          <button type="button" className={s.retry} onClick={() => void query.refetch()}>
            Retry
          </button>
        </div>
      </div>
    );
  }

  if (query.isPending || !view) {
    return (
      <div className={s.page}>
        <p className={s.loading}>Loading Smart OI…</p>
      </div>
    );
  }

  const isStale =
    dataMode === 'live' && query.dataUpdatedAt > 0 && now - query.dataUpdatedAt > STALE_AFTER_MS;

  return (
    <div className={s.page}>
      <SmartOiToolbar
        instrument={instrument}
        onCycle={cycle}
        expiry={expiry}
        expiries={expiryQuery.data?.expiries ?? []}
        resolvedExpiry={view.expiry_date}
        onExpiry={setExpiry}
        interval={interval}
        onInterval={setIntervalChoice}
        dataMode={dataMode}
        date={date}
        onDataMode={setDataMode}
        onDate={setDate}
        replay={replay}
        onReplay={setReplay}
        rangeMode={rangeMode}
        onRangeMode={setRangeMode}
        strikeMode={strikeMode}
        onStrikeMode={setStrikeMode}
        span={span}
        onSpan={setSpan}
        custom={custom}
        onCustom={setCustom}
        strikeLow={view.strike_low}
        strikeHigh={view.strike_high}
        now={now}
        updatedAt={query.dataUpdatedAt}
        period={REFETCH_MS}
        fetching={query.isFetching}
      />

      {view.data_quality !== 'intraday' ? (
        <p className={s.note} role="status">
          {view.data_quality === 'empty'
            ? 'No option-chain captures for this session, so the flow panes are empty. The price chart is real history.'
            : `Only the live chain is available${expiry ? ' for this expiry' : ''} — the archive holds the nearest expiry only, so the flow is shown as open-versus-now rather than bar by bar.`}
        </p>
      ) : null}

      {isStale ? (
        <p className={cx(s.note, s.stale)} role="status">
          The feed has not refreshed in over {Math.round(STALE_AFTER_MS / 1000)}s.
        </p>
      ) : null}

      {replay ? (
        <ReplayBar
          head={head}
          total={bars.length}
          playing={playing}
          speed={speed}
          at={bars[head]?.t}
          onHead={setHead}
          onPlaying={setPlaying}
          onSpeed={setSpeed}
          onExit={() => setReplay(false)}
        />
      ) : null}

      <div className={s.layout}>
        <PricePanel
          bars={shown.bars}
          smartOi={shown.smartOi}
          callVol={shown.call}
          putVol={shown.put}
          symbol={instrument.short}
          resetKey={`${instrument.symbol}-${interval}-${dataMode}-${historyDate ?? ''}`}
        />

        <div className={s.side}>
          <SeriesChart
            title="OI Change (Day)"
            subtitle="Open interest written on each side since the bell, and the spread between them."
            icon={<IconChart />}
            valueAxisName="OI change"
            lines={oiLines}
            timestamps={times}
            futures={view.fut}
            formatValue={fmtOi}
            formatPrice={fmtPrice}
            group={CHART_GROUP}
            head={frameHead}
            empty="No option-chain captures recorded for this session yet."
            compact
          />
          <SeriesChart
            title="Put-Call Ratios"
            subtitle="By open interest, and by the session's total traded volume."
            icon={<IconFx />}
            valueAxisName="Ratio"
            referenceLine={{ value: 1, label: 'PCR 1' }}
            lines={pcrLines}
            timestamps={times}
            futures={view.fut}
            formatValue={fmtRatio}
            formatPrice={fmtPrice}
            group={CHART_GROUP}
            head={frameHead}
            empty="No option-chain captures recorded for this session yet."
            compact
          />
        </div>
      </div>

      <div className={s.footer}>
        <span className={s.meta}>
          {view.interval} buckets · {bars.length} bars · {times.length} captures
          {view.open_is_estimated ? ' · open reconstructed from day change' : ''}
        </span>
        <button
          type="button"
          className={s.download}
          onClick={download}
          title="Download the plotted bars as CSV"
        >
          ↓ CSV
        </button>
      </div>
    </div>
  );
}
