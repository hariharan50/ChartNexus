<script lang="ts">
  import { formatPrice, formatSignedPercent, direction } from '$shared/formatting/numbers';
  import type { IndexQuote } from '$contexts/market-data/view-models';

  interface Props {
    quote: IndexQuote;
    selected?: boolean;
    onselect?: () => void;
  }

  let { quote, selected = false, onselect }: Props = $props();

  const dir = $derived(quote.changePercent !== undefined ? direction(quote.changePercent) : 'flat');
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
      <span class="pill {dir}">{formatSignedPercent(quote.changePercent)}</span>
    {/if}
  </span>
  <span class="accent {dir}" aria-hidden="true"></span>
</button>

<style>
  .card {
    position: relative;
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 0.5rem;
    width: 100%;
    padding: var(--mc-space-4) var(--mc-space-4) var(--mc-space-6);
    text-align: left;
    background: var(--mc-surface);
    border: 1px solid var(--mc-border);
    border-radius: var(--mc-radius-lg);
    box-shadow: var(--mc-shadow);
    overflow: hidden;
    cursor: pointer;
    transition:
      border-color var(--mc-duration-fast) ease,
      transform var(--mc-duration-fast) ease;
  }

  .card:hover {
    border-color: var(--mc-border-strong);
  }

  .card.selected {
    border-color: var(--mc-brand);
    box-shadow:
      0 0 0 1px var(--mc-brand),
      var(--mc-shadow);
  }

  .card.pending {
    cursor: default;
  }

  .label {
    font-size: var(--mc-text-xs);
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--mc-text-subtle);
  }

  .value {
    font-size: 2rem;
    font-weight: 700;
    letter-spacing: -0.02em;
    line-height: 1.05;
  }

  .card.pending .value {
    color: var(--mc-text-subtle);
  }

  .foot {
    display: flex;
    min-height: 1.25rem;
  }

  .pill {
    display: inline-flex;
    align-items: center;
    padding: 0.125rem 0.5rem;
    border-radius: 999px;
    font-size: var(--mc-text-xs);
    font-weight: 600;
  }

  .pill.up {
    color: var(--mc-bullish);
    background: var(--mc-bullish-weak);
  }

  .pill.down {
    color: var(--mc-bearish);
    background: var(--mc-bearish-weak);
  }

  .pill.flat {
    color: var(--mc-text-muted);
    background: var(--mc-surface-raised);
  }

  .await {
    font-size: var(--mc-text-xs);
    color: var(--mc-text-subtle);
  }

  .accent {
    position: absolute;
    left: 0;
    right: 0;
    bottom: 0;
    height: 3px;
  }

  .accent.up {
    background: var(--mc-bullish);
  }

  .accent.down {
    background: var(--mc-bearish);
  }

  .accent.flat {
    background: transparent;
  }
</style>
