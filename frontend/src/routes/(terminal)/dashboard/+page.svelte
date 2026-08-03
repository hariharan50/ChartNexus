<script lang="ts">
  import { toBackendSymbol, indexCard, vixCard, optionRows, metrics, aiSummary } from '$contexts/market-data/derive';
  import {
    marketStatusQuery,
    spotQuery,
    optionChainQuery
  } from '$contexts/market-data/queries.svelte';
  import type { IndexKey } from './dashboard-data';
  import DataSourceBadge from '$shared/ui/DataSourceBadge.svelte';
  import IndexCard from './components/IndexCard.svelte';
  import IndexTabs from './components/IndexTabs.svelte';
  import LiveBadge from './components/LiveBadge.svelte';
  import OptionChainCard from './components/OptionChainCard.svelte';
  import OptionsMetricsCard from './components/OptionsMetricsCard.svelte';
  import FiiDiiCard from './components/FiiDiiCard.svelte';
  import QuickActionsCard from './components/QuickActionsCard.svelte';
  import AiSummaryCard from './components/AiSummaryCard.svelte';

  let focused = $state<IndexKey>('NIFTY50');

  // Live queries. The three index spots are fixed; the option chain follows the
  // focused tab. All share the query cache the websocket stream will later feed.
  const statusQ = marketStatusQuery();
  const niftyQ = spotQuery('NIFTY');
  const sensexQ = spotQuery('SENSEX');
  const bankNiftyQ = spotQuery('BANKNIFTY');
  const chainQ = optionChainQuery(() => toBackendSymbol(focused));

  const indices = $derived([
    indexCard('NIFTY50', 'NIFTY 50', $niftyQ.data),
    indexCard('SENSEX', 'SENSEX', $sensexQ.data),
    indexCard('BANKNIFTY', 'BANK NIFTY', $bankNiftyQ.data),
    vixCard()
  ]);

  const chain = $derived($chainQ.data);
  const rows = $derived(chain ? optionRows(chain) : []);
  const chainMetrics = $derived(chain ? metrics(chain) : undefined);
  const ai = $derived(chainMetrics ? aiSummary(indices, chainMetrics) : undefined);

  const focusedLabel = $derived(indices.find((q) => q.key === focused)?.label ?? 'NIFTY 50');

  // Provenance for the source badge: prefer the chain, fall back to status.
  const provenance = $derived(chain?.provenance);
  const clock = $derived($statusQ.data?.time_ist ?? '—');
  const isLive = $derived($statusQ.data?.is_open ?? false);
</script>

<svelte:head>
  <title>Intelligence Dashboard · MarketCompass</title>
</svelte:head>

<div class="page">
  <header class="page-head">
    <div class="titles">
      <h1>Intelligence Dashboard</h1>
      <p>Live market intelligence — focused on {focusedLabel}</p>
    </div>
    <div class="controls">
      <IndexTabs value={focused} onchange={(k) => (focused = k)} />
      {#if provenance}
        <DataSourceBadge source={provenance.source} ageSeconds={provenance.age_seconds} />
      {/if}
      <LiveBadge time={clock} live={isLive} />
    </div>
  </header>

  <div class="indices">
    {#each indices as quote (quote.key)}
      <IndexCard
        {quote}
        selected={quote.key === focused}
        onselect={() => {
          if (quote.key !== 'INDIAVIX') focused = quote.key as IndexKey;
        }}
      />
    {/each}
  </div>

  <div class="main">
    <div class="left">
      {#if $chainQ.isError}
        <div class="panel-error" role="alert">
          <p>Couldn’t load the option chain.</p>
          <button type="button" onclick={() => $chainQ.refetch()}>Retry</button>
        </div>
      {:else}
        <OptionChainCard {rows} loading={$chainQ.isPending} />
      {/if}
    </div>
    <aside class="right">
      {#if chainMetrics}
        <OptionsMetricsCard metrics={chainMetrics} />
      {/if}
      <FiiDiiCard />
      <QuickActionsCard />
    </aside>
  </div>

  {#if ai}
    <AiSummaryCard summary={ai} />
  {/if}

  <p class="disclaimer">
    For educational and informational purposes only. MarketCompass is not a SEBI-registered
    investment adviser. Nothing here is investment advice, a recommendation, or a solicitation to
    buy or sell any security. Levels and signals are illustrative and derived from automated models
    that may be delayed or inaccurate. Markets carry risk — consult a registered financial adviser
    before trading.
  </p>
</div>

<style>
  .page {
    display: flex;
    flex-direction: column;
    gap: var(--mc-space-6);
    max-width: 84rem;
    margin: 0 auto;
    padding: var(--mc-space-6) var(--mc-space-6) var(--mc-space-8);
  }

  .page-head {
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    gap: var(--mc-space-4);
    flex-wrap: wrap;
  }

  h1 {
    margin: 0;
    font-size: var(--mc-text-2xl);
    font-weight: 700;
    letter-spacing: -0.02em;
  }

  .titles p {
    margin: 0.25rem 0 0;
    font-size: var(--mc-text-sm);
    color: var(--mc-text-muted);
  }

  .controls {
    display: flex;
    align-items: center;
    gap: var(--mc-space-3);
    flex-wrap: wrap;
  }

  .indices {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: var(--mc-space-4);
  }

  .main {
    display: grid;
    grid-template-columns: minmax(0, 2.1fr) minmax(0, 1fr);
    gap: var(--mc-space-4);
    align-items: start;
  }

  .right {
    display: flex;
    flex-direction: column;
    gap: var(--mc-space-4);
  }

  .panel-error {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: var(--mc-space-3);
    padding: var(--mc-space-6);
    background: var(--mc-surface);
    border: 1px solid var(--mc-border);
    border-radius: var(--mc-radius-lg);
    box-shadow: var(--mc-shadow);
    color: var(--mc-text-muted);
  }

  .panel-error button {
    min-height: var(--mc-control-h-sm);
    padding: 0 var(--mc-control-px);
    border: 1px solid var(--mc-border-strong);
    border-radius: var(--mc-radius);
    background: var(--mc-surface-raised);
    color: var(--mc-text);
    font-weight: 600;
    cursor: pointer;
  }

  .disclaimer {
    margin: 0;
    padding: var(--mc-space-4);
    border: 1px solid var(--mc-border);
    border-radius: var(--mc-radius);
    background: var(--mc-surface);
    font-size: var(--mc-text-xs);
    line-height: 1.6;
    color: var(--mc-text-subtle);
  }

  @media (max-width: 64rem) {
    .indices {
      grid-template-columns: repeat(2, 1fr);
    }

    .main {
      grid-template-columns: 1fr;
    }
  }

  @media (max-width: 40rem) {
    .page {
      padding: var(--mc-space-4);
      gap: var(--mc-space-4);
    }

    .indices {
      grid-template-columns: 1fr;
    }
  }
</style>
