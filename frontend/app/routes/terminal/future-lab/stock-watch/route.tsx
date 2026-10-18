import { useEffect, useMemo, useRef, useState } from 'react';
import { useInstruments } from '$contexts/instrument-catalog/queries';
import { useSymbolParam } from '$contexts/instrument-catalog/use-symbol-param';
import { useMarketStatusQuery } from '$contexts/market-data/queries';
import { cx } from '$shared/ui/cx';
import { hasNoRealData, toCandles, toVolume, type Interval } from '../../analyse/analyse-data';
import { vwap } from '../../analyse/indicators';
import {
  atmIv,
  basisOf,
  buildupCandidates,
  historicalVolatility,
  maxPain,
  rolloverPercent,
  sideStats,
  topOi,
  totals
} from './calc/analytics';
import type { OptionType } from './calc/black-scholes';
import { enrichChain, type EnrichedChain } from './calc/chain';
import { feedState, wire } from './calc/format';
import { levelsFrom } from './calc/levels';
import { NO_COSTS } from './calc/plan';
import AiAnalyst, { type EvidencePack } from './components/AiAnalyst';
import AlertsPanel from './components/AlertsPanel';
import ContractCompare from './components/ContractCompare';
import EventsPanel from './components/EventsPanel';
import FuturesPanel from './components/FuturesPanel';
import JournalPanel from './components/JournalPanel';
import LevelsPanel from './components/LevelsPanel';
import OiAnalytics from './components/OiAnalytics';
import OptionChainTable from './components/OptionChainTable';
import ScenarioPanel from './components/ScenarioPanel';
import StockHeader, { FeedNotice } from './components/StockHeader';
import SummaryTiles, { summaryTiles } from './components/SummaryTiles';
import TradePlanner, { type PlannerInputs, type Selection } from './components/TradePlanner';
import UnderlyingChart, { INTERVALS } from './components/UnderlyingChart';
import VolatilityPanel from './components/VolatilityPanel';
import {
  boardRow,
  useStockChainQuery,
  useStockExpiriesQuery,
  useStockFuturesBoardQuery,
  useStockFuturesQuery,
  useStockHistoryQuery,
  useStockSpotQuery
} from './data';
import { type AlertKind, type FiredAlert, evaluateAlerts, useStockWatchStore } from './store';
import s from './stock-watch.module.css';
import type { Route } from './+types/route';

export const meta: Route.MetaFunction = () => [{ title: 'Stock Watch · Future Lab · ChartNexus' }];

/** Future Lab is a single-stock desk, so the page opens on a stock. */
const DEFAULT_SYMBOL = 'RELIANCE';

type Tab =
  'oi' | 'volatility' | 'levels' | 'compare' | 'scenario' | 'events' | 'ai' | 'journal' | 'alerts';

const TABS: { id: Tab; label: string }[] = [
  { id: 'oi', label: 'OI analytics' },
  { id: 'volatility', label: 'Volatility & greeks' },
  { id: 'levels', label: 'Technical levels' },
  { id: 'compare', label: 'Compare contracts' },
  { id: 'scenario', label: 'Scenarios' },
  { id: 'events', label: 'Events' },
  { id: 'ai', label: 'AI analyst' },
  { id: 'journal', label: 'Journal' },
  { id: 'alerts', label: 'Alerts' }
];

const EMPTY_CHAIN: EnrichedChain = {
  rows: [],
  spot: 0,
  expiry: '',
  expiries: [],
  daysToExpiry: 0,
  totalCallOi: 0,
  totalPutOi: 0,
  greeksUnavailable: true
};

const DEFAULT_PLANNER: PlannerInputs = {
  lots: 1,
  entry: 0,
  stop: 0,
  target: 0,
  capital: 100_000,
  riskPercent: 1,
  maxDailyLoss: 0,
  lossSoFarToday: 0
};

/**
 * Stock Watch — a single-stock F&O analysis desk.
 *
 * **What this page is for.** Everything else in Future Lab is a board: the
 * whole universe ranked by one measure. This is the opposite — one underlying,
 * read from every angle that bears on a decision, in the order a trader
 * actually asks the questions: what is the stock doing, what is the futures
 * tape saying, where is the options book positioned, which contract is
 * tradeable, and what does it cost if the thesis is wrong.
 *
 * **Three rules run through every panel**, and they are the reason this reads
 * differently from a data dump:
 *
 * * *Absent is not zero.* A figure the feed did not quote shows a dash with an
 *   explanation. A 0.00 PCR and an empty put side are different claims.
 * * *Provider figures and model figures never share a column.* Delta is the
 *   broker's; gamma, theta and vega are this app's Black-Scholes, labelled.
 * * *A classification carries its evidence.* Every build-up chip, every zone,
 *   every structure read shows the rule that produced it, because open
 *   interest cannot tell you who is on which side of a contract.
 *
 * **It plans trades; it does not place them.** There is no order path from
 * this page, by design.
 */
export default function StockWatch() {
  const [symbol, setSymbol] = useSymbolParam(DEFAULT_SYMBOL);
  const [interval, setInterval] = useState<Interval>('15m');
  const [tab, setTab] = useState<Tab>('oi');
  const [expiry, setExpiry] = useState<string | undefined>(undefined);
  const [selection, setSelection] = useState<Selection | undefined>(undefined);
  const [planner, setPlanner] = useState<PlannerInputs>(DEFAULT_PLANNER);
  const [shortlist, setShortlist] = useState<Set<string>>(() => new Set());
  const [fired, setFired] = useState<FiredAlert[]>([]);

  const store = useStockWatchStore();
  useEffect(() => store.init(), [store]);

  // -- data ------------------------------------------------------------------

  const { instruments, isLoading: catalogLoading } = useInstruments();
  const instrument = useMemo(
    () => instruments.find((entry) => entry.symbol === symbol),
    [instruments, symbol]
  );

  const statusQ = useMarketStatusQuery();
  const spotQ = useStockSpotQuery(symbol);
  const futuresQ = useStockFuturesQuery(symbol);
  const expiriesQ = useStockExpiriesQuery(symbol);
  const chainQ = useStockChainQuery(symbol, expiry);
  const days = INTERVALS.find((entry) => entry.value === interval)?.days ?? 30;
  const historyQ = useStockHistoryQuery(symbol, interval, days);
  const nearBoardQ = useStockFuturesBoardQuery(0);
  const nextBoardQ = useStockFuturesBoardQuery(1);
  // Daily closes for realised volatility — a separate, slow series from the
  // chart's, because the chart may be on 1-minute bars and a realised vol
  // computed off those is a different (and much larger) number.
  const dailyQ = useStockHistoryQuery(symbol, '1d', 180);

  // Expiry follows the instrument unless the reader chose one. Resetting on a
  // symbol change is the point: last week's NIFTY expiry is not a contract on
  // this stock, and asking for it returns someone else's book or nothing.
  const expiries = useMemo(
    () => expiriesQ.data?.expiries ?? chainQ.data?.expiries ?? [],
    [expiriesQ.data, chainQ.data]
  );
  const previousSymbol = useRef(symbol);
  useEffect(() => {
    if (previousSymbol.current !== symbol) {
      previousSymbol.current = symbol;
      setExpiry(undefined);
      setSelection(undefined);
      setShortlist(new Set());
    }
  }, [symbol]);

  // -- derivations -----------------------------------------------------------

  const chain = useMemo(
    () => (chainQ.data ? enrichChain(chainQ.data) : EMPTY_CHAIN),
    [chainQ.data]
  );

  const candles = useMemo(() => toCandles(historyQ.data), [historyQ.data]);
  const volume = useMemo(() => toVolume(historyQ.data), [historyQ.data]);
  const sessionVwap = useMemo(() => {
    const points = vwap(candles, volume);
    return points[points.length - 1]?.value;
  }, [candles, volume]);

  const levels = useMemo(
    () => levelsFrom(candles, volume, interval, sessionVwap != null ? { vwap: sessionVwap } : {}),
    [candles, volume, interval, sessionVwap]
  );

  const dailyCloses = useMemo(
    () => (dailyQ.data?.candles ?? []).map((candle) => Number(candle.close)),
    [dailyQ.data]
  );

  const spot = wire(spotQ.data?.price);
  const futuresPrice = wire(futuresQ.data?.price);
  const basis = useMemo(
    () => (futuresPrice != null && spot != null ? basisOf(futuresPrice, spot) : undefined),
    [futuresPrice, spot]
  );

  const nearRow = useMemo(() => boardRow(nearBoardQ.data, symbol), [nearBoardQ.data, symbol]);
  const nextRow = useMemo(() => boardRow(nextBoardQ.data, symbol), [nextBoardQ.data, symbol]);

  const sums = useMemo(() => totals(chain.rows), [chain.rows]);
  const atm = useMemo(() => atmIv(chain), [chain]);
  const hv = useMemo(() => historicalVolatility(dailyCloses), [dailyCloses]);

  const marketOpen = statusQ.data?.is_open ?? false;
  const feed = useMemo(
    () =>
      feedState(
        spotQ.data?.provenance.source ?? 'unavailable',
        spotQ.data?.provenance.age_seconds,
        marketOpen
      ),
    [spotQ.data, marketOpen]
  );

  // -- alerts ----------------------------------------------------------------

  const worstSpread = useMemo(() => {
    let worst = 0;
    for (const row of chain.rows) {
      for (const leg of [row.ce, row.pe]) {
        if (leg?.liquidity.spreadPercent != null) {
          worst = Math.max(worst, leg.liquidity.spreadPercent);
        }
      }
    }
    return worst || undefined;
  }, [chain.rows]);

  const maxOiChangePercent = useMemo(() => {
    let worst = 0;
    for (const row of chain.rows) {
      for (const leg of [row.ce, row.pe]) {
        if (leg?.oiChangePercent != null) worst = Math.max(worst, Math.abs(leg.oiChangePercent));
      }
    }
    return worst || undefined;
  }, [chain.rows]);

  const alertSignature = `${spot ?? ''}:${feed.freshness}:${chain.expiry}:${maxOiChangePercent ?? ''}`;
  useEffect(() => {
    if (!store.hydrated) return;
    const now = Date.now();
    const hits = evaluateAlerts(
      store.alerts,
      {
        symbol,
        ...(spot != null ? { price: spot } : {}),
        ...(levels.relativeVolume != null ? { relativeVolume: levels.relativeVolume } : {}),
        ...(maxOiChangePercent != null ? { maxOiChangePercent } : {}),
        ...(nearRow?.state ? { futuresBuildup: nearRow.state } : {}),
        ...(atm != null ? { atmIv: atm } : {}),
        ...(worstSpread != null ? { worstSpreadPercent: worstSpread } : {}),
        feedStale: feed.freshness === 'stale' || feed.freshness === 'very_stale'
      },
      now
    );
    if (hits.length === 0) return;
    setFired((previous) => [...hits, ...previous].slice(0, 50));
    for (const hit of hits) store.markFired(hit.ruleId, now);
    // Signature rather than the raw objects: the chain re-enriches into a new
    // array on every fifteen-second poll, and depending on it would re-evaluate
    // (and re-fire) every rule each time even when nothing moved.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [alertSignature, store.hydrated, store.alerts.length]);

  // -- interactions ----------------------------------------------------------

  const pickContract = (strike: number, type: OptionType) => {
    const row = chain.rows.find((candidate) => candidate.strike === strike);
    const leg = type === 'CE' ? row?.ce : row?.pe;
    if (!leg) return;
    setSelection({
      strike,
      type,
      expiry: chain.expiry,
      leg,
      lotSize: chain.lotSize ?? instrument?.lot_size
    });
    // Seed the planner from the live premium. A stop at 60% of entry and a
    // target at 160% are starting points the reader will overwrite, not
    // advice — they exist so the panel is never showing a divide-by-zero.
    setPlanner((previous) => ({
      ...previous,
      entry: leg.ltp,
      stop: Number((leg.ltp * 0.6).toFixed(2)),
      target: Number((leg.ltp * 1.6).toFixed(2))
    }));
  };

  const toggleShortlist = (strike: number, type: OptionType) =>
    setShortlist((previous) => {
      const key = `${strike}:${type}`;
      const next = new Set(previous);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });

  const saveToJournal = () => {
    if (!selection) return;
    store.addJournalEntry({
      tradeDate: new Date().toISOString().slice(0, 10),
      symbol,
      type: selection.type,
      strike: selection.strike,
      expiry: selection.expiry,
      lotSize: selection.lotSize ?? 0,
      lots: planner.lots,
      entry: planner.entry,
      stop: planner.stop,
      target: planner.target,
      setup: '',
      rationale: '',
      exitReason: '',
      context: {
        ...(spot != null ? { spot } : {}),
        ...(basis ? { futuresBasisPercent: basis.percent } : {}),
        ...(atm != null ? { atmIv: atm } : {}),
        ...(sums.pcrOi != null ? { pcrOi: sums.pcrOi } : {}),
        structure: levels.structure.state
      },
      violations: [],
      notes: ''
    });
    setTab('journal');
  };

  // -- evidence for the analyst ---------------------------------------------

  const pack = useMemo<EvidencePack>(() => {
    const missing: string[] = [];
    if (feed.freshness === 'simulated') missing.push('all market data is simulated, not live');
    if (feed.freshness !== 'fresh' && feed.freshness !== 'simulated') missing.push(feed.message);
    if (chain.rows.length === 0) missing.push('no option chain loaded');
    if (chain.greeksUnavailable) missing.push('the chain carries no implied volatility');
    if (hv == null) missing.push('not enough daily history for realised volatility');
    missing.push('no IV percentile or IV rank — this app has no single-stock IV archive');
    missing.push('no corporate events, results dates, F&O ban status or news feed is configured');
    if (nearRow?.open_interest == null) missing.push('futures open interest was not priced');
    if (levels.previousSessionMissing)
      missing.push('the candle series has no complete prior session');

    const liquidityWarnings: string[] = [];
    for (const row of chain.rows) {
      for (const leg of [row.ce, row.pe]) {
        if (leg && leg.liquidity.grade === 'illiquid') {
          liquidityWarnings.push(`${row.strike} ${leg.type}: ${leg.liquidity.reasons.join('; ')}`);
        }
      }
    }

    return {
      symbol,
      asOf: spotQ.data?.provenance.fetched_at ?? new Date().toISOString(),
      dataSource: feed.source,
      feedWarning: feed.message,
      marketOpen,
      ...(spot != null ? { spot } : {}),
      ...(wire(spotQ.data?.change_percent) != null
        ? { changePercent: wire(spotQ.data?.change_percent) }
        : {}),
      structure: levels.structure.state,
      structureRule: levels.structure.rule,
      ...(levels.atr != null ? { atr: levels.atr } : {}),
      ...(levels.relativeVolume != null ? { relativeVolume: levels.relativeVolume } : {}),
      ...(levels.gap && levels.gap.kind !== 'none'
        ? {
            gap: `${levels.gap.kind} ${levels.gap.percent.toFixed(2)}%${levels.gap.filled ? ' (filled)' : ''}`
          }
        : {}),
      levels: levels.levels.map((level) => ({
        label: level.label,
        price: level.price,
        timeframe: level.timeframe
      })),
      ...(futuresPrice != null ? { futuresPrice } : {}),
      ...(basis ? { futuresBasisPercent: basis.percent } : {}),
      futuresState: nearRow?.state ?? 'unknown',
      ...(nearRow?.open_interest != null ? { futuresOi: nearRow.open_interest } : {}),
      ...(wire(nearRow?.oi_change_percent) != null
        ? { futuresOiChangePercent: wire(nearRow?.oi_change_percent) }
        : {}),
      ...(rolloverPercent(
        nearRow?.open_interest ?? undefined,
        nextRow?.open_interest ?? undefined
      ) != null
        ? {
            rolloverPercent: rolloverPercent(
              nearRow?.open_interest ?? undefined,
              nextRow?.open_interest ?? undefined
            )
          }
        : {}),
      ...(chain.expiry ? { expiry: chain.expiry } : {}),
      daysToExpiry: chain.daysToExpiry,
      ...(atm != null ? { atmIv: atm } : {}),
      ...(hv != null ? { historicalVol: hv } : {}),
      ...(sums.pcrOi != null ? { pcrOi: sums.pcrOi } : {}),
      ...(sums.pcrVolume != null ? { pcrVolume: sums.pcrVolume } : {}),
      ...(maxPain(chain.rows) != null ? { maxPain: maxPain(chain.rows) } : {}),
      topCallOi: topOi(sideStats(chain.rows, 'CE'), 3).map((stat) => ({
        strike: stat.strike,
        oi: stat.oi
      })),
      topPutOi: topOi(sideStats(chain.rows, 'PE'), 3).map((stat) => ({
        strike: stat.strike,
        oi: stat.oi
      })),
      buildups: buildupCandidates(chain.rows, 8).map(({ strike, leg }) => ({
        strike,
        type: leg.type,
        state: leg.buildup.state
      })),
      liquidityWarnings: liquidityWarnings.slice(0, 8),
      missing
    } as EvidencePack;
  }, [
    symbol,
    spotQ.data,
    feed,
    marketOpen,
    spot,
    levels,
    futuresPrice,
    basis,
    nearRow,
    nextRow,
    chain,
    atm,
    hv,
    sums
  ]);

  const tiles = useMemo(
    () =>
      summaryTiles({
        ...(futuresPrice != null ? { futuresPrice } : {}),
        ...(wire(futuresQ.data?.change_percent) != null
          ? { futuresChangePercent: wire(futuresQ.data?.change_percent) }
          : {}),
        ...(basis ? { basis } : {}),
        ...(atm != null ? { atmIv: atm } : {}),
        ivQuoted: !chain.greeksUnavailable,
        ...(sums.pcrOi != null ? { pcrOi: sums.pcrOi } : {}),
        callOi: sums.callOi,
        putOi: sums.putOi,
        ...(levels.atr != null ? { atr: levels.atr } : {}),
        atrTimeframe: interval,
        ...(spot != null ? { spot } : {})
      }),
    [
      futuresPrice,
      futuresQ.data,
      basis,
      atm,
      chain.greeksUnavailable,
      sums,
      levels.atr,
      interval,
      spot
    ]
  );

  // -- render ----------------------------------------------------------------

  return (
    <div className={s.page}>
      <StockHeader
        symbol={symbol}
        instrument={instrument}
        instruments={instruments}
        catalogLoading={catalogLoading}
        onSymbol={setSymbol}
        spot={spotQ.data}
        futures={futuresQ.data}
        marketOpen={marketOpen}
        sessionDate={statusQ.data?.session_date}
        feed={feed}
        expiries={expiries}
        expiry={expiry ?? (chain.expiry || undefined)}
        onExpiry={setExpiry}
        futuresExpiry={futuresQ.data?.expiry}
        watched={store.watchlist.includes(symbol)}
        onToggleWatch={() => store.toggleWatch(symbol)}
      />

      <FeedNotice feed={feed} source={feed.source} />

      <SummaryTiles tiles={tiles} />

      <div className={s.mainGrid}>
        <div className={s.stack}>
          <UnderlyingChart
            symbol={symbol}
            candles={candles}
            volume={volume}
            interval={interval}
            onInterval={setInterval}
            levels={levels}
            loading={historyQ.isPending}
            noRealData={hasNoRealData(historyQ.data)}
          />

          {chainQ.isError ? (
            <p className={cx(s.notice, s.noticeDanger)} role="alert">
              <span>
                Could not load the option chain for {symbol}.
                <button
                  type="button"
                  className={s.action}
                  style={{ marginLeft: 'var(--cn-space-2)' }}
                  onClick={() => void chainQ.refetch()}
                >
                  Retry
                </button>
              </span>
            </p>
          ) : (
            <OptionChainTable
              chain={chain}
              loading={chainQ.isPending}
              onPick={pickContract}
              shortlist={shortlist}
              onShortlist={toggleShortlist}
            />
          )}
        </div>

        <aside className={s.stack}>
          <FuturesPanel
            symbol={symbol}
            futures={futuresQ.data}
            spot={spot}
            basis={basis}
            nearRow={nearRow}
            nextRow={nextRow}
            hasOpenInterest={nearBoardQ.data?.has_open_interest ?? true}
            loading={futuresQ.isPending}
          />
          <TradePlanner
            selection={selection}
            inputs={planner}
            onInputs={setPlanner}
            costs={store.costs ?? NO_COSTS}
            onCosts={store.setCosts}
            onJournal={saveToJournal}
          />
        </aside>
      </div>

      <div className={s.tabs} role="tablist" aria-label="Analysis sections">
        {TABS.map((entry) => (
          <button
            key={entry.id}
            type="button"
            role="tab"
            aria-selected={entry.id === tab}
            className={cx(s.tab, entry.id === tab && s.tabOn)}
            onClick={() => setTab(entry.id)}
          >
            {entry.label}
          </button>
        ))}
      </div>

      {tab === 'oi' ? <OiAnalytics chain={chain} /> : null}
      {tab === 'volatility' ? (
        <VolatilityPanel chain={chain} dailyCloses={dailyCloses} dailyBars={dailyCloses.length} />
      ) : null}
      {tab === 'levels' ? (
        <LevelsPanel levels={levels} candles={candles} spot={spot} timeframe={interval} />
      ) : null}
      {tab === 'compare' ? (
        <ContractCompare
          chain={chain}
          shortlist={shortlist}
          onClear={() => setShortlist(new Set())}
          onRemove={(key) =>
            setShortlist((previous) => {
              const next = new Set(previous);
              next.delete(key);
              return next;
            })
          }
        />
      ) : null}
      {tab === 'scenario' ? (
        <ScenarioPanel
          selection={selection}
          spot={spot}
          daysToExpiry={chain.daysToExpiry}
          entryPremium={planner.entry}
          lots={planner.lots}
        />
      ) : null}
      {tab === 'events' ? (
        <EventsPanel
          symbol={symbol}
          expiry={chain.expiry || undefined}
          futuresExpiry={futuresQ.data?.expiry}
          daysToExpiry={chain.daysToExpiry}
        />
      ) : null}
      {tab === 'ai' ? <AiAnalyst symbol={symbol} pack={pack} /> : null}
      {tab === 'journal' ? (
        <JournalPanel
          symbol={symbol}
          entries={store.journal}
          onRemove={store.removeJournalEntry}
          onUpdate={(entry) => {
            store.removeJournalEntry(entry.id);
            store.addJournalEntry(entry);
          }}
        />
      ) : null}
      {tab === 'alerts' ? (
        <AlertsPanel
          symbol={symbol}
          rules={store.alerts}
          fired={fired}
          watchlist={store.watchlist}
          onAdd={(kind: AlertKind, threshold: number) =>
            store.addAlert({ symbol, kind, threshold, enabled: true })
          }
          onToggle={store.toggleAlert}
          onRemove={store.removeAlert}
          onPick={setSymbol}
        />
      ) : null}

      <p className={s.disclaimer}>
        For educational and informational purposes only. ChartNexus is not a SEBI-registered
        investment adviser. Nothing on this page is investment advice, a recommendation, or a
        solicitation to buy or sell any security. Classifications, zones and model values are
        derived from automated rules and a Black-Scholes approximation under stated assumptions;
        they may be delayed, incomplete or wrong. This page analyses and plans trades — it cannot
        place them. Markets carry risk, and option buyers can lose the entire premium. Consult a
        registered financial adviser before trading.
      </p>
    </div>
  );
}
