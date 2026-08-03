<script lang="ts">
  import { formatPrice, formatSignedPercent, direction } from '$shared/formatting/numbers';
  import type { IndexQuote } from '../dashboard-data';
  import Pill from './Pill.svelte';

  interface Props {
    quote: IndexQuote;
    selected?: boolean;
    onselect?: () => void;
  }

  let { quote, selected = false, onselect }: Props = $props();

  const dir = $derived(quote.changePercent !== undefined ? direction(quote.changePercent) : 'flat');
  const tone = $derived(dir === 'up' ? 'bullish' : dir === 'down' ? 'bearish' : 'neutral');
</script>

<button
  type="button"
  class="card"
  class:selected
  class:pending={quote.pending}
  aria-pressed={selected}
  onclick={onselect}
>
  <span class="label">{quote.label}</span>
  <span class="value mc-numeric">{quote.pending ? '—' : formatPrice(quote.value)}</span>
  <span class="foot">
    {#if quote.pending}
      <span class="await">Awaiting market data</span>
    {:else if quote.changePercent !== undefined}
      <Pill {tone}>{formatSignedPercent(quote.changePercent)}</Pill>
    {:else if quote.tag}
      <Pill tone="accent">{quote.tag}</Pill>
    {/if}
  </span>
</button>

<style>
  .card {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 0.375rem;
    width: 100%;
    padding: var(--mc-space-4);
    text-align: left;
    background: var(--mc-surface);
    border: 1px solid var(--mc-border);
    border-radius: var(--mc-radius-lg);
    box-shadow: var(--mc-shadow);
    cursor: pointer;
    transition:
      border-color var(--mc-duration-fast) ease,
      transform var(--mc-duration-fast) ease;
  }

  .card:hover {
    border-color: var(--mc-border-strong);
  }

  .card.selected {
    border-color: var(--mc-accent);
    box-shadow:
      0 0 0 1px var(--mc-accent),
      var(--mc-shadow);
  }

  .label {
    font-size: var(--mc-text-xs);
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--mc-text-subtle);
  }

  .value {
    font-size: 1.625rem;
    font-weight: 700;
    letter-spacing: -0.02em;
    line-height: 1.1;
  }

  .foot {
    display: flex;
    min-height: 1.25rem;
  }

  .card.pending {
    cursor: default;
  }

  .card.pending .value {
    color: var(--mc-text-subtle);
  }

  .await {
    font-size: var(--mc-text-xs);
    color: var(--mc-text-subtle);
  }
</style>
