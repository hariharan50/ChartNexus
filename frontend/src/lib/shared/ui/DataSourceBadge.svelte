<script lang="ts">
  import type { DataSourceName } from '$contexts/broker-connections/types';

  /**
   * States where a number came from.
   *
   * A "connected" indicator elsewhere must not be read as "this price is live" —
   * a cached or simulated figure looks identical on a chart, and only this badge
   * distinguishes them.
   */

  interface Props {
    source: DataSourceName;
    ageSeconds?: number;
    compact?: boolean;
  }

  let { source, ageSeconds = 0, compact = false }: Props = $props();

  const label = $derived({ live: 'Live', cached: 'Cached', mock: 'Simulated' }[source] ?? source);

  const detail = $derived(
    source === 'live' ? '' : source === 'cached' ? formatAge(ageSeconds) : 'not real data'
  );

  function formatAge(seconds: number): string {
    if (seconds < 60) return `${Math.round(seconds)}s old`;
    if (seconds < 3600) return `${Math.round(seconds / 60)}m old`;
    return `${Math.round(seconds / 3600)}h old`;
  }
</script>

<span class="badge {source}" class:compact title={detail || undefined}>
  <span class="dot" aria-hidden="true"></span>
  {label}
  {#if detail && !compact}
    <span class="detail">· {detail}</span>
  {/if}
</span>

<style>
  .badge {
    display: inline-flex;
    align-items: center;
    gap: 0.375rem;
    padding: 0.125rem 0.5rem;
    border: 1px solid transparent;
    border-radius: 999px;
    font-size: var(--mc-text-xs);
    font-weight: 600;
    white-space: nowrap;
  }

  .dot {
    width: 0.4375rem;
    height: 0.4375rem;
    border-radius: 50%;
    background: currentColor;
  }

  .live {
    color: var(--mc-live);
    border-color: color-mix(in srgb, var(--mc-live) 35%, transparent);
    background: color-mix(in srgb, var(--mc-live) 12%, transparent);
  }

  .cached {
    color: var(--mc-stale);
    border-color: color-mix(in srgb, var(--mc-stale) 35%, transparent);
    background: color-mix(in srgb, var(--mc-stale) 12%, transparent);
  }

  /* Deliberately the loudest of the three: simulated numbers must never be
     mistaken for market data. */
  .mock {
    color: var(--mc-danger);
    border-color: color-mix(in srgb, var(--mc-danger) 40%, transparent);
    background: color-mix(in srgb, var(--mc-danger) 12%, transparent);
  }

  .detail {
    font-weight: 400;
    opacity: 0.85;
  }

  .compact {
    padding: 0 0.375rem;
  }
</style>
