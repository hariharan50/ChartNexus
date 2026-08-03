<script lang="ts">
  import IconBank from '$shared/ui/icons/IconBank.svelte';
  import IconClock from '$shared/ui/icons/IconClock.svelte';
  import Panel from './Panel.svelte';

  interface Flow {
    label: string;
    /** Net cash in ₹ crore. `null` until the data feed lands. */
    value: number | null;
  }

  interface Props {
    flows?: Flow[];
  }

  let {
    flows = [
      { label: 'FII Cash', value: null },
      { label: 'DII Cash', value: null }
    ]
  }: Props = $props();

  function formatCr(value: number): string {
    const sign = value > 0 ? '+' : value < 0 ? '−' : '';
    return `${sign}₹${Math.abs(value).toLocaleString('en-IN')} Cr`;
  }
</script>

<Panel title="FII / DII Flow">
  {#snippet icon()}<IconBank />{/snippet}
  {#snippet children()}
    <div class="grid">
      {#each flows as flow (flow.label)}
        <div class="cell">
          <p class="label">{flow.label}</p>
          {#if flow.value === null}
            <span class="awaiting">
              <span class="ico" aria-hidden="true"><IconClock /></span>
              Awaiting market data
            </span>
          {:else}
            <p class="value mc-numeric" class:up={flow.value > 0} class:down={flow.value < 0}>
              {formatCr(flow.value)}
            </p>
          {/if}
        </div>
      {/each}
    </div>
  {/snippet}
</Panel>

<style>
  .grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: var(--mc-space-4);
  }

  .cell:first-child {
    border-right: 1px solid var(--mc-border);
    padding-right: var(--mc-space-4);
  }

  .label {
    margin: 0 0 var(--mc-space-2);
    font-size: var(--mc-text-xs);
    font-weight: 600;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    color: var(--mc-text-subtle);
  }

  .awaiting {
    display: inline-flex;
    align-items: center;
    gap: 0.375rem;
    padding: 0.3125rem 0.625rem;
    border-radius: var(--mc-radius);
    background: var(--mc-surface-raised);
    border: 1px dashed var(--mc-border-strong);
    font-size: var(--mc-text-xs);
    color: var(--mc-text-subtle);
  }

  .ico {
    display: inline-flex;
    color: var(--mc-warning);
  }

  .ico :global(svg) {
    width: 0.875rem;
    height: 0.875rem;
  }

  .value {
    margin: 0;
    font-size: var(--mc-text-lg);
    font-weight: 700;
  }

  .up {
    color: var(--mc-bullish);
  }

  .down {
    color: var(--mc-bearish);
  }
</style>
