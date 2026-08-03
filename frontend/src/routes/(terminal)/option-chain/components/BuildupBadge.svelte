<script lang="ts">
  import type { BuildUp } from '$contexts/market-data/view-models';

  interface Props {
    buildup?: BuildUp | undefined;
  }

  let { buildup }: Props = $props();

  // Arrow + short code + tone for each build-up label. Longs sit on the deeper
  // shade of their colour, unwinding/covering on the brighter one.
  const MAP: Record<BuildUp, { arrow: string; code: string; tone: string }> = {
    'Short Covering': { arrow: '↑', code: 'SC', tone: 'sc' },
    'Long Build-up': { arrow: '↗', code: 'L', tone: 'l' },
    'Short Build-up': { arrow: '↘', code: 'S', tone: 's' },
    'Long Unwinding': { arrow: '↓', code: 'LU', tone: 'lu' }
  };

  const info = $derived(buildup ? MAP[buildup] : undefined);
</script>

{#if info}
  <span class="badge {info.tone}" title={buildup}>
    <span aria-hidden="true">{info.arrow}</span>
    {info.code}
  </span>
{:else}
  <span class="badge none">—</span>
{/if}

<style>
  .badge {
    display: inline-flex;
    align-items: center;
    gap: 0.125rem;
    padding: 0.125rem 0.375rem;
    border-radius: var(--mc-radius-sm);
    font-size: var(--mc-text-xs);
    font-weight: 700;
    line-height: 1.2;
    white-space: nowrap;
  }

  .sc {
    background: var(--mc-bullish);
    color: #fff;
  }

  .l {
    background: color-mix(in srgb, var(--mc-bullish) 62%, black);
    color: #fff;
  }

  .s {
    background: var(--mc-bearish);
    color: #fff;
  }

  .lu {
    background: color-mix(in srgb, var(--mc-bearish) 45%, black);
    color: color-mix(in srgb, var(--mc-bearish) 45%, white);
  }

  .none {
    color: var(--mc-text-subtle);
    font-weight: 400;
  }
</style>
