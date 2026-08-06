import { useMemo, useState } from 'react';
import type { FuturesQuote } from '$contexts/broker-connections/types';
import {
  indexCard,
  ivPercentile,
  metrics,
  toBackendSymbol,
  vixCard
} from '$contexts/market-data/derive';
import {
  useFuturesQuery,
  useMarketStatusQuery,
  useOptionChainQuery,
  useSpotQuery
} from '$contexts/market-data/queries';
import type { IndexKey } from '$contexts/market-data/view-models';
import { formatInt } from '$shared/formatting/numbers';
import IndexTabs from '../dashboard/components/IndexTabs';
import LiveBadge from '../dashboard/components/LiveBadge';
import FuturesCard from './components/FuturesCard';
import MetricTile from './components/MetricTile';
import SpotCard from './components/SpotCard';
import s from './route.module.css';
import type { Route } from './+types/route';

export const meta: Route.MetaFunction = () => [{ title: 'Advanced Dashboard · MarketCompass' }];

const dec = (v: string | null | undefined) => (v != null ? Number.parseFloat(v) : undefined);

function toFut(label: string, q: FuturesQuote | undefined) {
  return {
    label,
    value: dec(q?.price),
    changePercent: dec(q?.change_percent),
    volume: q?.volume,
    contract: q?.contract,
    dayHigh: dec(q?.day_high),
    dayLow: dec(q?.day_low)
  };
}

export default function AdvancedDashboard() {
  const [focused, setFocused] = useState<IndexKey>('NIFTY50');

  // Live queries. Spots are fixed; the option chain follows the focused tab and
  // feeds the metrics strip. All share the cache the websocket stream will fill.
  const statusQ = useMarketStatusQuery();
  const niftyQ = useSpotQuery('NIFTY');
  const sensexQ = useSpotQuery('SENSEX');
  const bankNiftyQ = useSpotQuery('BANKNIFTY');
  const chainQ = useOptionChainQuery(toBackendSymbol(focused));

  const indices = useMemo(
    () => [
      indexCard('NIFTY50', 'NIFTY 50', niftyQ.data),
      indexCard('SENSEX', 'SENSEX', sensexQ.data),
      indexCard('BANKNIFTY', 'BANK NIFTY', bankNiftyQ.data)
    ],
    [niftyQ.data, sensexQ.data, bankNiftyQ.data]
  );

  // Front-month futures for all three indices. The backend resolves the active
  // monthly contract and rolls it after expiry, so these track the near-month
  // future without any client-side series handling.
  const niftyFutQ = useFuturesQuery('NIFTY');
  const sensexFutQ = useFuturesQuery('SENSEX');
  const bankFutQ = useFuturesQuery('BANKNIFTY');

  const futures = useMemo(
    () => [
      toFut('NIFTY Futures', niftyFutQ.data),
      toFut('SENSEX Futures', sensexFutQ.data),
      toFut('Bank Nifty Futures', bankFutQ.data)
    ],
    [niftyFutQ.data, sensexFutQ.data, bankFutQ.data]
  );

  const chain = chainQ.data;
  const chainMetrics = useMemo(() => (chain ? metrics(chain) : undefined), [chain]);

  // ATM implied volatility from the leg at the ATM strike (CE, else PE).
  const atmIv = useMemo(() => {
    if (!chain?.atm_strike) return undefined;
    const atm = Number.parseFloat(chain.atm_strike);
    const row = chain.strikes.find((strike) => Number.parseFloat(strike.strike) === atm);
    const iv = row?.ce?.iv ?? row?.pe?.iv;
    return iv != null ? Number.parseFloat(iv) : undefined;
  }, [chain]);

  const pcr = chainMetrics?.pcr;
  const maxPain = chainMetrics?.maxPain;

  const focusedLabel = indices.find((q) => q.key === focused)?.label ?? 'NIFTY 50';
  const vix = vixCard(chain);
  const ivPct = ivPercentile(chain);
  const clock = statusQ.data?.time_ist ?? '—';
  const isLive = statusQ.data?.is_open ?? false;

  return (
    <div className={s.page}>
      <header className={s.pageHead}>
        <div className={s.titles}>
          <h1>Advanced Dashboard</h1>
          <p>Deep market intelligence — focused on {focusedLabel}</p>
        </div>
        <div className={s.controls}>
          <IndexTabs value={focused} onChange={setFocused} />
          <LiveBadge time={clock} live={isLive} />
        </div>
      </header>

      <section className={s.section}>
        <h2 className={s.sectionTitle}>Market Snapshot</h2>

        <div className={s.grid3}>
          {indices.map((quote) => (
            <SpotCard
              key={quote.key}
              quote={quote}
              selected={quote.key === focused}
              onSelect={() => setFocused(quote.key as IndexKey)}
            />
          ))}
        </div>

        <div className={s.grid3}>
          {futures.map((f) => (
            <FuturesCard
              key={f.label}
              label={f.label}
              value={f.value}
              changePercent={f.changePercent}
              volume={f.volume}
              contract={f.contract}
              dayHigh={f.dayHigh}
              dayLow={f.dayLow}
            />
          ))}
        </div>

        <div className={s.gridMetrics}>
          <MetricTile label="PCR (OI)" value={pcr != null ? pcr.toFixed(2) : '—'} />
          <MetricTile label="India VIX" value={vix.pending ? '—' : vix.value.toFixed(2)} />
          <MetricTile
            label="Max Pain"
            value={maxPain != null && Number.isFinite(maxPain) ? formatInt(maxPain) : '—'}
            tone="warning"
          />
          <MetricTile label="ATM IV" value={atmIv != null ? atmIv.toFixed(2) : '—'} />
          <MetricTile label="IV Percentile" value={ivPct != null ? ivPct.toFixed(1) : '—'} />
        </div>
      </section>
    </div>
  );
}
