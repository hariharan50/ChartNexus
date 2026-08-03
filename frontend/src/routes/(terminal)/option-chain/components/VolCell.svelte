<script lang="ts">
  import { compactIndian, ordinal, type Side } from '../chain-model';

  interface Props {
    value?: number | undefined;
    /** 1-based volume rank on this side, or undefined when no volume. */
    rank?: number | undefined;
    /** The #1 volume on this side — denominator for "% of highest". */
    top: number;
    side: Side;
  }

  let { value, rank, top, side }: Props = $props();

  const inTop3 = $derived(rank != null && rank <= 3);
  const pctOfTop = $derived(value != null && top > 0 ? Math.round((value / top) * 100) : undefined);
</script>

<td class="vol {side}">
  <span class="wrap">
    <span class="chip" class:top3={inTop3}>{compactIndian(value)}</span>
    {#if rank != null && pctOfTop != null}
      <span class="tip" role="tooltip">
        <span class="tip-line">Volume Rank: {ordinal(rank)}</span>
        <span class="tip-sub">{pctOfTop}% of {ordinal(1)} highest</span>
      </span>
    {/if}
  </span>
</td>

<style>
  .vol {
    padding: var(--mc-space-2) var(--mc-space-3);
    white-space: nowrap;
  }

  .vol.ce {
    text-align: right;
  }

  .vol.pe {
    text-align: left;
  }

  .wrap {
    position: relative;
    display: inline-flex;
  }

  .chip {
    border-radius: var(--mc-radius-sm);
    padding: 0.0625rem 0.25rem;
    color: var(--mc-text);
    font-family: var(--mc-font-mono);
    font-variant-numeric: tabular-nums;
  }

  .chip.top3 {
    background: color-mix(in srgb, var(--mc-bullish) 20%, transparent);
    color: var(--mc-bullish);
    font-weight: 600;
  }

  .tip {
    position: absolute;
    top: 100%;
    margin-top: 0.25rem;
    z-index: var(--mc-z-dropdown);
    display: none;
    flex-direction: column;
    gap: 0.125rem;
    padding: var(--mc-space-2) var(--mc-space-3);
    border: 1px solid var(--mc-border);
    border-radius: var(--mc-radius);
    background: var(--mc-surface);
    box-shadow: var(--mc-shadow);
    white-space: nowrap;
  }

  /* Anchor the tooltip to the cell's outer edge (left for calls, right for
     puts) so it opens away from the strike column. */
  .ce .tip {
    left: 0;
  }

  .pe .tip {
    right: 0;
  }

  .wrap:hover .tip,
  .wrap:focus-within .tip {
    display: flex;
  }

  .tip-line {
    font-size: var(--mc-text-xs);
    font-weight: 600;
    color: var(--mc-text);
  }

  .tip-sub {
    font-size: var(--mc-text-xs);
    color: var(--mc-text-muted);
  }
</style>
