<script lang="ts">
  import { toBackendSymbol, optionRows, metrics } from '$contexts/market-data/derive';
  import { marketStatusQuery, optionChainQuery } from '$contexts/market-data/queries.svelte';
  import type { IndexKey } from '$contexts/market-data/view-models';
  import type { OptionChain } from '$contexts/broker-connections/types';
  import { formatInt, formatPrice } from '$shared/formatting/numbers';
  import DataSourceBadge from '$shared/ui/DataSourceBadge.svelte';
  import IndexTabs from '../dashboard/components/IndexTabs.svelte';
  import LiveBadge from '../dashboard/components/LiveBadge.svelte';
  import StatTile from './components/StatTile.svelte';
  import OptionChainTable from './components/OptionChainTable.svelte';

  let focused = $state<IndexKey>('NIFTY50');

  const statusQ = marketStatusQuery();
  const chainQ = optionChainQuery(() => toBackendSymbol(focused));

  const chain = $derived($chainQ.data);
  const rows = $derived(chain ? optionRows(chain) : []);
  const m = $derived(chain ? metrics(chain) : undefined);
  const pcrVol = $derived(chain ? pcrByVolume(chain) : Number.NaN);

  const provenance = $derived(chain?.provenance);
  const clock = $derived($statusQ.data?.time_ist ?? '—');
  const isLive = $derived($statusQ.data?.is_open ?? false);

  function n(value: string | null | undefined): number {
    return value == null ? Number.NaN : Number.parseFloat(value);
  }

  /** Volume-weighted put/call ratio; NaN when there is no call volume. */
  function pcrByVolume(c: OptionChain): number {
    let ce = 0;
    let pe = 0;
    for (const s of c.strikes) {
      ce += s.ce?.volume ?? 0;
      pe += s.pe?.volume ?? 0;
    }
    return ce > 0 ? pe / ce : Number.NaN;
  }

  /** A wide-band bias label for a PCR figure. */
  function pcrLabel(pcr: number): string {
    if (Number.isNaN(pcr)) return '—';
    if (pcr >= 1.2) return 'Bullish';
    if (pcr <= 0.8) return 'Bearish';
    return 'Neutral';
  }

  const writer = $derived.by(() => {
    switch (m?.writingPosture) {
      case 'PUT_WRITERS_DOMINANT':
        return { label: 'Put Writers', pill: 'Dominant', tone: 'bullish' as const };
      case 'CALL_WRITERS_DOMINANT':
        return { label: 'Call Writers', pill: 'Dominant', tone: 'bearish' as const };
      case 'BALANCED':
        return { label: 'Balanced', pill: 'Neutral', tone: 'neutral' as const };
      default:
        return { label: '—', pill: '', tone: 'neutral' as const };
    }
  });

  const dash = (value: string) => (chain ? value : '—');
</script>

<svelte:head>
  <title>Options Analytics · MarketCompass</title>
</svelte:head>

<div class="page">
  <header class="page-head">
    <div class="titles">
      <h1>Options Analytics</h1>
      <p>Chain, PCR, max pain &amp; OI build-up</p>
    </div>
    <div class="controls">
      <IndexTabs value={focused} onchange={(k) => (focused = k)} />
      {#if provenance}
        <DataSourceBadge source={provenance.source} ageSeconds={provenance.age_seconds} />
      {/if}
      <LiveBadge time={clock} live={isLive} />
    </div>
  </header>

  <!-- Headline figures: one connected strip. -->
  <div class="summary">
    <div class="cell">
      <p class="s-label">Spot</p>
      <p class="s-value mc-numeric">{dash(formatPrice(n(chain?.spot_price)))}</p>
    </div>
    <div class="cell">
      <p class="s-label">ATM</p>
      <p class="s-value mc-numeric">{chain?.atm_strike ? formatInt(n(chain.atm_strike)) : '—'}</p>
    </div>
    <div class="cell">
      <p class="s-label">Call OI</p>
      <p class="s-value mc-numeric">{dash(formatInt(chain?.total_call_oi ?? 0))}</p>
    </div>
    <div class="cell">
      <p class="s-label">Put OI</p>
      <p class="s-value mc-numeric">{dash(formatInt(chain?.total_put_oi ?? 0))}</p>
    </div>
  </div>

  <!-- Derived metrics. -->
  <div class="metrics">
    <StatTile
      label="PCR (OI)"
      value={m ? m.pcr.toFixed(2) : '—'}
      sub={m ? pcrLabel(m.pcr) : undefined}
    />
    <StatTile
      label="PCR (Vol)"
      value={Number.isNaN(pcrVol) ? '—' : pcrVol.toFixed(2)}
      sub={chain ? pcrLabel(pcrVol) : undefined}
    />
    <StatTile label="Max Pain" value={m ? formatInt(m.maxPain) : '—'} />
    <StatTile label="Support" value={m ? formatInt(m.support) : '—'} valueTone="bullish" />
    <StatTile label="Resistance" value={m ? formatInt(m.resistance) : '—'} valueTone="bearish" />
    <StatTile label="Writing" value={writer.label} pill={writer.pill} pillTone={writer.tone} />
  </div>

  {#if $chainQ.isError}
    <div class="panel-error" role="alert">
      <p>Couldn’t load the option chain.</p>
      <button type="button" onclick={() => $chainQ.refetch()}>Retry</button>
    </div>
  {:else}
    <OptionChainTable {rows} loading={$chainQ.isPending} />
  {/if}

  <p class="disclaimer">
    For educational and informational purposes only. MarketCompass is not a SEBI-registered
    investment adviser. Support, resistance, max pain and build-up labels are illustrative, derived
    from the live option chain, and may be delayed or inaccurate. Markets carry risk — consult a
    registered financial adviser before trading.
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

  .summary {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    background: var(--mc-surface);
    border: 1px solid var(--mc-border);
    border-radius: var(--mc-radius-lg);
    box-shadow: var(--mc-shadow);
    overflow: hidden;
  }

  .summary .cell {
    padding: var(--mc-space-4) var(--mc-space-5);
    border-left: 1px solid var(--mc-border);
  }

  .summary .cell:first-child {
    border-left: none;
  }

  .s-label {
    margin: 0;
    font-size: var(--mc-text-xs);
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--mc-text-subtle);
  }

  .s-value {
    margin: var(--mc-space-2) 0 0;
    font-size: var(--mc-text-2xl);
    font-weight: 700;
    letter-spacing: -0.02em;
  }

  .metrics {
    display: grid;
    grid-template-columns: repeat(6, 1fr);
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

  @media (max-width: 72rem) {
    .metrics {
      grid-template-columns: repeat(3, 1fr);
    }
  }

  @media (max-width: 48rem) {
    .summary {
      grid-template-columns: repeat(2, 1fr);
    }

    .summary .cell:nth-child(3) {
      border-left: none;
    }

    .summary .cell:nth-child(n + 3) {
      border-top: 1px solid var(--mc-border);
    }

    .metrics {
      grid-template-columns: repeat(2, 1fr);
    }
  }

  @media (max-width: 40rem) {
    .page {
      padding: var(--mc-space-4);
      gap: var(--mc-space-4);
    }
  }
</style>
