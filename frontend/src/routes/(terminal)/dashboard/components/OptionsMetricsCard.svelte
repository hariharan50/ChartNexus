<script lang="ts">
  import IconTarget from '$shared/ui/icons/IconTarget.svelte';
  import { formatInt } from '$shared/formatting/numbers';
  import type { OptionsMetrics } from '../dashboard-data';
  import Panel from './Panel.svelte';

  interface Props {
    metrics: OptionsMetrics;
  }

  let { metrics }: Props = $props();

  const postureLabel = $derived(metrics.writingPosture.replaceAll('_', ' '));
</script>

<Panel title="Options Metrics">
  {#snippet icon()}<IconTarget />{/snippet}
  {#snippet children()}
    <dl class="grid">
      <div class="cell">
        <dt>PCR (OI)</dt>
        <dd class="mc-numeric">{metrics.pcr.toFixed(2)}</dd>
      </div>
      <div class="cell">
        <dt>Max Pain</dt>
        <dd class="mc-numeric">{formatInt(metrics.maxPain)}</dd>
      </div>
      <div class="cell">
        <dt>Support</dt>
        <dd class="mc-numeric support">{formatInt(metrics.support)}</dd>
      </div>
      <div class="cell">
        <dt>Resistance</dt>
        <dd class="mc-numeric resistance">{formatInt(metrics.resistance)}</dd>
      </div>
    </dl>

    <div class="posture">
      <dt>Writing Posture</dt>
      <dd>{postureLabel}</dd>
    </div>
  {/snippet}
</Panel>

<style>
  .grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0;
    margin: 0;
  }

  .cell {
    padding: var(--mc-space-2) var(--mc-space-3);
  }

  .cell:nth-child(odd) {
    border-right: 1px solid var(--mc-border);
  }

  .cell:nth-child(-n + 2) {
    border-bottom: 1px solid var(--mc-border);
    padding-bottom: var(--mc-space-3);
  }

  .cell:nth-child(n + 3) {
    padding-top: var(--mc-space-3);
  }

  dt {
    font-size: var(--mc-text-xs);
    font-weight: 600;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    color: var(--mc-text-subtle);
  }

  dd {
    margin: 0.25rem 0 0;
    font-size: var(--mc-text-xl);
    font-weight: 700;
    letter-spacing: -0.01em;
  }

  .support {
    color: var(--mc-bullish);
  }

  .resistance {
    color: var(--mc-bearish);
  }

  .posture {
    margin-top: var(--mc-space-3);
    padding-top: var(--mc-space-3);
    border-top: 1px solid var(--mc-border);
  }

  .posture dd {
    font-family: var(--mc-font-mono);
    font-size: var(--mc-text-base);
    letter-spacing: 0.01em;
  }
</style>
