<script lang="ts">
  import {
    toBackendSymbol,
    indexCard,
    vixCard,
    ivPercentile,
    metrics
  } from '$contexts/market-data/derive';
  import {
    marketStatusQuery,
    spotQuery,
    futuresQuery,
    optionChainQuery
  } from '$contexts/market-data/queries.svelte';
  import type { IndexKey } from '$contexts/market-data/view-models';
  import type { FuturesQuote } from '$contexts/broker-connections/types';
  import { formatInt } from '$shared/formatting/numbers';
  import IndexTabs from '../dashboard/components/IndexTabs.svelte';
  import LiveBadge from '../dashboard/components/LiveBadge.svelte';
  import SpotCard from './components/SpotCard.svelte';
  import FuturesCard from './components/FuturesCard.svelte';
  import MetricTile from './components/MetricTile.svelte';

  let focused = $state<IndexKey>('NIFTY50');

  // Live queries. Spots are fixed; the option chain follows the focused tab and
  // feeds the metrics strip. All share the cache the websocket stream will fill.
  const statusQ = marketStatusQuery();
  const niftyQ = spotQuery('NIFTY');
  const sensexQ = spotQuery('SENSEX');
  const bankNiftyQ = spotQuery('BANKNIFTY');
  const chainQ = optionChainQuery(() => toBackendSymbol(focused));

  const indices = $derived([
    indexCard('NIFTY50', 'NIFTY 50', $niftyQ.data),
    indexCard('SENSEX', 'SENSEX', $sensexQ.data),
    indexCard('BANKNIFTY', 'BANK NIFTY', $bankNiftyQ.data)
  ]);

  // Front-month futures for all three indices. The backend resolves the active
  // monthly contract and rolls it after expiry, so these track the near-month
  // future without any client-side series handling.
  const niftyFutQ = futuresQuery('NIFTY');
  const sensexFutQ = futuresQuery('SENSEX');
  const bankFutQ = futuresQuery('BANKNIFTY');

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

  const futures = $derived([
    toFut('NIFTY Futures', $niftyFutQ.data),
    toFut('SENSEX Futures', $sensexFutQ.data),
    toFut('Bank Nifty Futures', $bankFutQ.data)
  ]);

  const chain = $derived($chainQ.data);
  const chainMetrics = $derived(chain ? metrics(chain) : undefined);

  // ATM implied volatility from the leg at the ATM strike (CE, else PE).
  const atmIv = $derived.by(() => {
    if (!chain?.atm_strike) return undefined;
    const atm = Number.parseFloat(chain.atm_strike);
    const row = chain.strikes.find((s) => Number.parseFloat(s.strike) === atm);
    const iv = row?.ce?.iv ?? row?.pe?.iv;
    return iv != null ? Number.parseFloat(iv) : undefined;
  });

  const pcr = $derived(chainMetrics?.pcr);
  const maxPain = $derived(chainMetrics?.maxPain);

  const focusedLabel = $derived(indices.find((q) => q.key === focused)?.label ?? 'NIFTY 50');
  const vix = $derived(vixCard(chain));
  const ivPct = $derived(ivPercentile(chain));
  const clock = $derived($statusQ.data?.time_ist ?? '—');
  const isLive = $derived($statusQ.data?.is_open ?? false);
</script>

<svelte:head>
  <title>Advanced Dashboard · MarketCompass</title>
</svelte:head>

<div class="page">
  <header class="page-head">
    <div class="titles">
      <h1>Advanced Dashboard</h1>
      <p>Deep market intelligence — focused on {focusedLabel}</p>
    </div>
    <div class="controls">
      <IndexTabs value={focused} onchange={(k) => (focused = k)} />
      <LiveBadge time={clock} live={isLive} />
    </div>
  </header>

  <section class="section">
    <h2 class="section-title">Market Snapshot</h2>

    <div class="grid-3">
      {#each indices as quote (quote.key)}
        <SpotCard
          {quote}
          selected={quote.key === focused}
          onselect={() => (focused = quote.key as IndexKey)}
        />
      {/each}
    </div>

    <div class="grid-3">
      {#each futures as f (f.label)}
        <FuturesCard
          label={f.label}
          value={f.value}
          changePercent={f.changePercent}
          volume={f.volume}
          contract={f.contract}
          dayHigh={f.dayHigh}
          dayLow={f.dayLow}
        />
      {/each}
    </div>

    <div class="grid-metrics">
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

  .section {
    display: flex;
    flex-direction: column;
    gap: var(--mc-space-4);
  }

  .section-title {
    display: flex;
    align-items: center;
    gap: var(--mc-space-3);
    margin: 0;
    font-size: var(--mc-text-xs);
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--mc-text-subtle);
  }

  .section-title::after {
    content: '';
    flex: 1;
    height: 1px;
    background: var(--mc-border);
  }

  .grid-3 {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: var(--mc-space-4);
  }

  .grid-metrics {
    display: grid;
    grid-template-columns: repeat(5, minmax(0, 1fr));
    gap: var(--mc-space-4);
  }

  @media (max-width: 64rem) {
    .grid-3 {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }

    .grid-metrics {
      grid-template-columns: repeat(3, minmax(0, 1fr));
    }
  }

  @media (max-width: 40rem) {
    .page {
      padding: var(--mc-space-4);
      gap: var(--mc-space-4);
    }

    .grid-3,
    .grid-metrics {
      grid-template-columns: 1fr;
    }
  }
</style>
