import { useMemo, useState } from 'react';
import {
  aiSummary,
  gapReading,
  indexCard,
  metrics,
  optionRows,
  toBackendSymbol,
  vixCard
} from '$contexts/market-data/derive';
import { useFiiDiiSummaryQuery } from '$contexts/market-breadth/queries';
import {
  useMarketStatusQuery,
  useOptionChainQuery,
  useSpotQuery
} from '$contexts/market-data/queries';
import DataSourceBadge from '$shared/ui/DataSourceBadge';
import AiSummaryCard from './components/AiSummaryCard';
import FiiDiiCard from './components/FiiDiiCard';
import GapIndicatorCard from './components/GapIndicatorCard';
import IndexCard from './components/IndexCard';
import IndexTabs from './components/IndexTabs';
import LiveBadge from './components/LiveBadge';
import MarketPhase from './components/MarketPhase';
import OptionChainCard from './components/OptionChainCard';
import OptionsMetricsCard from './components/OptionsMetricsCard';
import type { IndexKey } from './dashboard-data';
import s from './route.module.css';
import type { Route } from './+types/route';

export const meta: Route.MetaFunction = () => [{ title: 'Intelligence Dashboard · ChartNexus' }];

export default function Dashboard() {
  const [focused, setFocused] = useState<IndexKey>('NIFTY50');

  // Live queries. The three index spots are fixed; the option chain follows the
  // focused tab. All share the query cache the websocket stream will later feed.
  const statusQ = useMarketStatusQuery();
  const niftyQ = useSpotQuery('NIFTY');
  const sensexQ = useSpotQuery('SENSEX');
  const bankNiftyQ = useSpotQuery('BANKNIFTY');
  const chainQ = useOptionChainQuery(toBackendSymbol(focused));
  // Same query key the Future Lab's FII/DII pages use, so the rail card and
  // the page it links to share one fetch and can never disagree.
  const flowQ = useFiiDiiSummaryQuery();

  const chain = chainQ.data;

  // Memoised because `aiSummary` reads it and the option-chain derivations
  // below are O(strikes); a fresh array every render would redo all that work.
  const indices = useMemo(
    () => [
      indexCard('NIFTY50', 'NIFTY 50', niftyQ.data),
      indexCard('SENSEX', 'SENSEX', sensexQ.data),
      indexCard('BANKNIFTY', 'BANK NIFTY', bankNiftyQ.data),
      vixCard(chain)
    ],
    [niftyQ.data, sensexQ.data, bankNiftyQ.data, chain]
  );

  const rows = useMemo(() => (chain ? optionRows(chain) : []), [chain]);
  const chainMetrics = useMemo(() => (chain ? metrics(chain) : undefined), [chain]);
  const ai = useMemo(
    () => (chainMetrics ? aiSummary(indices, chainMetrics) : undefined),
    [indices, chainMetrics]
  );

  const focusedLabel = indices.find((q) => q.key === focused)?.label ?? 'NIFTY 50';

  // The gap card reads the focused index. Its spot query is already running
  // above for the index strip, so following the tab costs no extra request.
  const focusedSpotQ =
    focused === 'SENSEX' ? sensexQ : focused === 'BANKNIFTY' ? bankNiftyQ : niftyQ;
  const gap = useMemo(
    () => gapReading(focusedLabel, focusedSpotQ.data),
    [focusedLabel, focusedSpotQ.data]
  );

  // Provenance for the source badge: prefer the chain, fall back to status.
  const provenance = chain?.provenance;
  const isLive = statusQ.data?.is_open ?? false;

  return (
    <div className={s.page}>
      <header className={s.pageHead}>
        <div className={s.titles}>
          <h1>Intelligence Dashboard</h1>
          <p>Live market intelligence — focused on {focusedLabel}</p>
        </div>
        <div className={s.controls}>
          <IndexTabs value={focused} onChange={setFocused} />
          {provenance ? (
            <DataSourceBadge source={provenance.source} ageSeconds={provenance.age_seconds} />
          ) : null}
          <LiveBadge live={isLive} />
        </div>
      </header>

      <MarketPhase />

      <div className={s.indices}>
        {indices.map((quote) => (
          <IndexCard
            key={quote.key}
            quote={quote}
            selected={quote.key === focused}
            onSelect={() => {
              if (quote.key !== 'INDIAVIX') setFocused(quote.key as IndexKey);
            }}
          />
        ))}
      </div>

      <div className={s.main}>
        <div className={s.left}>
          {chainQ.isError ? (
            <div className={s.panelError} role="alert">
              <p>Couldn’t load the option chain.</p>
              <button type="button" onClick={() => void chainQ.refetch()}>
                Retry
              </button>
            </div>
          ) : (
            <OptionChainCard rows={rows} loading={chainQ.isPending} />
          )}
        </div>
        <aside className={s.right}>
          <GapIndicatorCard reading={gap} loading={focusedSpotQ.isPending} label={focusedLabel} />
          {chainMetrics ? <OptionsMetricsCard metrics={chainMetrics} /> : null}
          <FiiDiiCard summary={flowQ.data} loading={flowQ.isPending} />
        </aside>
      </div>

      {ai ? <AiSummaryCard summary={ai} /> : null}

      <p className={s.disclaimer}>
        For educational and informational purposes only. ChartNexus is not a SEBI-registered
        investment adviser. Nothing here is investment advice, a recommendation, or a solicitation
        to buy or sell any security. Levels and signals are illustrative and derived from automated
        models that may be delayed or inaccurate. Markets carry risk — consult a registered
        financial adviser before trading.
      </p>
    </div>
  );
}
