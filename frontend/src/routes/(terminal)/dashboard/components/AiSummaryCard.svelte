<script lang="ts">
  import IconBrain from '$shared/ui/icons/IconBrain.svelte';
  import { formatPrice } from '$shared/formatting/numbers';
  import type { AiSummary } from '../dashboard-data';
  import Panel from './Panel.svelte';

  interface Props {
    summary: AiSummary;
  }

  let { summary }: Props = $props();

  const vixNote = $derived(
    summary.vix === undefined
      ? ''
      : summary.vix < 15
        ? 'VIX within normal range'
        : summary.vix < 20
          ? 'VIX slightly elevated'
          : 'VIX elevated — expect wider swings'
  );
</script>

<Panel accent title="AI Market Summary">
  {#snippet icon()}<IconBrain />{/snippet}
  {#snippet children()}
    <p class="summary">
      {#each summary.biases as b, i (b.label)}
        {b.label} AI bias:
        <strong class:bull={b.bias === 'Bullish'} class:bear={b.bias === 'Bearish'}>{b.bias}</strong
        >{#if b.confidence}&nbsp;<span class="conf">({b.confidence}% confidence)</span>{/if}.{i <
        summary.biases.length - 1
          ? ' '
          : ''}
      {/each}
      {#if summary.vix !== undefined}India VIX at {summary.vix.toFixed(1)} — {vixNote}.
      {/if}PCR at
      {summary.pcr.toFixed(2)}. Support {formatPrice(summary.support, 1)} | Resistance
      {formatPrice(summary.resistance, 1)}.
    </p>
  {/snippet}
</Panel>

<style>
  .summary {
    margin: 0;
    font-size: var(--mc-text-sm);
    line-height: 1.65;
    color: var(--mc-text-muted);
  }

  strong {
    color: var(--mc-text);
    font-weight: 700;
  }

  .bull {
    color: var(--mc-bullish);
  }

  .bear {
    color: var(--mc-bearish);
  }

  .conf {
    color: var(--mc-text-subtle);
  }
</style>
