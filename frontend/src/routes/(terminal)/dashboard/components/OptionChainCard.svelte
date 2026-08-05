<script lang="ts">
  import IconChart from '$shared/ui/icons/IconChart.svelte';
  import {
    formatInt,
    formatSignedInt,
    formatPrice,
    formatPercent,
    direction
  } from '$shared/formatting/numbers';
  import { buildUpTone, type OptionRow } from '../dashboard-data';
  import Panel from './Panel.svelte';
  import Pill from './Pill.svelte';

  interface Props {
    rows: OptionRow[];
    loading?: boolean;
  }

  let { rows, loading = false }: Props = $props();

  /** Strike-count choices for the header toggle; 6 keeps the default compact. */
  const STRIKE_CHOICES = [6, 10, 20] as const;
  let visibleStrikes = $state<number>(STRIKE_CHOICES[0]);

  /**
   * Rows arrive sorted by strike (PE then CE per strike). Show only a window of
   * `visibleStrikes` strikes centred on the ATM strike, so the default view is
   * tight and the toggle expands it symmetrically around spot.
   */
  const visibleRows = $derived.by(() => {
    // Group rows into strikes, preserving order.
    const strikes: OptionRow[][] = [];
    let currentStrike: number | null = null;
    for (const row of rows) {
      if (row.strike !== currentStrike) {
        currentStrike = row.strike;
        strikes.push([]);
      }
      strikes[strikes.length - 1]!.push(row);
    }

    if (strikes.length <= visibleStrikes) return rows;

    const atmIndex = strikes.findIndex((group) => group.some((r) => r.atm));
    const centre = atmIndex === -1 ? Math.floor(strikes.length / 2) : atmIndex;
    let start = centre - Math.floor(visibleStrikes / 2);
    start = Math.max(0, Math.min(start, strikes.length - visibleStrikes));

    return strikes.slice(start, start + visibleStrikes).flat();
  });
</script>

<Panel title="Option Chain" subtitle="Top strikes around spot">
  {#snippet icon()}<IconChart />{/snippet}
  {#snippet actions()}
    <div class="strike-toggle" role="group" aria-label="Strikes to show">
      {#each STRIKE_CHOICES as choice (choice)}
        <button
          type="button"
          class:active={visibleStrikes === choice}
          aria-pressed={visibleStrikes === choice}
          onclick={() => (visibleStrikes = choice)}
        >
          {choice}
        </button>
      {/each}
    </div>
  {/snippet}
  {#snippet children()}
    <div class="scroll">
      <table>
        <thead>
          <tr>
            <th class="strike">Strike</th>
            <th>Type</th>
            <th class="num">OI</th>
            <th class="num">OI Chg</th>
            <th class="num">LTP</th>
            <th class="num">IV</th>
            <th>Build-up</th>
          </tr>
        </thead>
        <tbody>
          {#each visibleRows as row (row.strike + row.type)}
            {@const dir = direction(row.oiChange)}
            <tr class:atm={row.atm}>
              <td class="strike">
                <span class="mc-numeric">{formatInt(row.strike)}</span>
                {#if row.atm}<Pill tone="accent" subtle>ATM</Pill>{/if}
              </td>
              <td>
                <Pill tone={row.type === 'CE' ? 'bullish' : 'bearish'}>{row.type}</Pill>
              </td>
              <td class="num mc-numeric">{formatInt(row.oi)}</td>
              <td class="num mc-numeric" class:up={dir === 'up'} class:down={dir === 'down'}>
                {formatSignedInt(row.oiChange)}
              </td>
              <td class="num mc-numeric">{formatPrice(row.ltp)}</td>
              <td class="num mc-numeric muted">
                {Number.isNaN(row.iv) ? '—' : formatPercent(row.iv)}
              </td>
              <td><Pill tone={buildUpTone(row.buildUp)}>{row.buildUp}</Pill></td>
            </tr>
          {/each}
        </tbody>
      </table>
      {#if rows.length === 0}
        <p class="empty">{loading ? 'Loading option chain…' : 'No strikes available.'}</p>
      {/if}
    </div>
  {/snippet}
</Panel>

<style>
  .scroll {
    overflow-x: auto;
  }

  .strike-toggle {
    display: inline-flex;
    padding: 2px;
    gap: 2px;
    border: 1px solid var(--mc-border);
    border-radius: var(--mc-radius);
    background: var(--mc-surface-raised);
  }

  .strike-toggle button {
    min-width: 2rem;
    padding: 0.25rem 0.5rem;
    border: none;
    border-radius: calc(var(--mc-radius) - 2px);
    background: transparent;
    color: var(--mc-text-subtle);
    font-size: var(--mc-text-xs);
    font-weight: 600;
    font-variant-numeric: tabular-nums;
    cursor: pointer;
    transition:
      background 0.12s ease,
      color 0.12s ease;
  }

  .strike-toggle button:hover {
    color: var(--mc-text);
  }

  .strike-toggle button.active {
    background: var(--mc-accent);
    color: var(--mc-accent-contrast, #fff);
  }

  .empty {
    margin: 0;
    padding: var(--mc-space-6) var(--mc-space-3);
    text-align: center;
    font-size: var(--mc-text-sm);
    color: var(--mc-text-subtle);
  }

  table {
    width: 100%;
    border-collapse: collapse;
    font-size: var(--mc-text-sm);
  }

  th {
    padding: 0 var(--mc-space-3) var(--mc-space-2);
    text-align: left;
    font-size: var(--mc-text-xs);
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--mc-text-subtle);
    border-bottom: 1px solid var(--mc-border);
    white-space: nowrap;
  }

  th.num {
    text-align: right;
  }

  td {
    padding: var(--mc-space-2) var(--mc-space-3);
    border-bottom: 1px solid var(--mc-border);
    white-space: nowrap;
  }

  tbody tr:last-child td {
    border-bottom: none;
  }

  tbody tr:hover {
    background: var(--mc-surface-raised);
  }

  tr.atm {
    background: color-mix(in srgb, var(--mc-accent) 6%, transparent);
  }

  tr.atm:hover {
    background: color-mix(in srgb, var(--mc-accent) 10%, transparent);
  }

  .strike {
    display: flex;
    align-items: center;
    gap: var(--mc-space-2);
    font-weight: 600;
  }

  td.strike {
    font-size: var(--mc-text-base);
  }

  .num {
    text-align: right;
  }

  .muted {
    color: var(--mc-text-muted);
  }

  .up {
    color: var(--mc-bullish);
    font-weight: 600;
  }

  .down {
    color: var(--mc-bearish);
    font-weight: 600;
  }
</style>
