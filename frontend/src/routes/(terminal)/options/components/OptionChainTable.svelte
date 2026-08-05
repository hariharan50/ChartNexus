<script lang="ts">
  import IconChart from '$shared/ui/icons/IconChart.svelte';
  import {
    formatInt,
    formatSignedInt,
    formatPrice,
    formatPercent,
    direction
  } from '$shared/formatting/numbers';
  import { buildUpTone, type OptionRow, type BuildUp } from '$contexts/market-data/view-models';
  import Panel from '../../dashboard/components/Panel.svelte';
  import Pill from '../../dashboard/components/Pill.svelte';

  interface Props {
    rows: OptionRow[];
    loading?: boolean;
  }

  let { rows, loading = false }: Props = $props();

  type Filter = 'all' | 'CE' | 'PE';
  let filter = $state<Filter>('all');

  const FILTERS: { key: Filter; label: string }[] = [
    { key: 'all', label: 'All' },
    { key: 'CE', label: 'CE' },
    { key: 'PE', label: 'PE' }
  ];

  const LEGEND: BuildUp[] = ['Long Build-up', 'Short Build-up', 'Long Unwinding', 'Short Covering'];

  // The chain arrives as PE-then-CE per strike; this page shows CE first, grouped
  // by strike ascending. Filtering to a single leg keeps that ordering.
  const visibleRows = $derived(
    [...rows]
      .filter((row) => filter === 'all' || row.type === filter)
      .sort((a, b) => a.strike - b.strike || (a.type === 'CE' ? -1 : 1))
  );
</script>

<Panel title="Option Chain" subtitle="Colour-coded by OI build-up">
  {#snippet icon()}<IconChart />{/snippet}
  {#snippet actions()}
    <div class="filter" role="group" aria-label="Filter option type">
      {#each FILTERS as choice (choice.key)}
        <button
          type="button"
          class:active={filter === choice.key}
          aria-pressed={filter === choice.key}
          onclick={() => (filter = choice.key)}
        >
          {choice.label}
        </button>
      {/each}
    </div>
  {/snippet}
  {#snippet children()}
    <div class="legend" aria-hidden="true">
      {#each LEGEND as tag (tag)}
        <span class="legend-item {buildUpTone(tag)}">
          <span class="dot"></span>{tag}
        </span>
      {/each}
    </div>

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
      {#if visibleRows.length === 0}
        <p class="empty">{loading ? 'Loading option chain…' : 'No strikes available.'}</p>
      {/if}
    </div>
  {/snippet}
</Panel>

<style>
  .filter {
    display: inline-flex;
    padding: 2px;
    gap: 2px;
    border: 1px solid var(--mc-border);
    border-radius: var(--mc-radius);
    background: var(--mc-surface-raised);
  }

  .filter button {
    min-width: 2.5rem;
    padding: 0.25rem 0.625rem;
    border: none;
    border-radius: calc(var(--mc-radius) - 2px);
    background: transparent;
    color: var(--mc-text-subtle);
    font-size: var(--mc-text-xs);
    font-weight: 600;
    cursor: pointer;
    transition:
      background 0.12s ease,
      color 0.12s ease;
  }

  .filter button:hover {
    color: var(--mc-text);
  }

  .filter button.active {
    background: var(--mc-accent);
    color: #fff;
  }

  .legend {
    display: flex;
    flex-wrap: wrap;
    gap: var(--mc-space-4);
    padding-bottom: var(--mc-space-3);
    margin-bottom: var(--mc-space-1);
    border-bottom: 1px solid var(--mc-border);
  }

  .legend-item {
    display: inline-flex;
    align-items: center;
    gap: 0.4375rem;
    font-size: var(--mc-text-xs);
    font-weight: 600;
    color: var(--mc-text-muted);
  }

  .legend-item .dot {
    width: 0.5rem;
    height: 0.5rem;
    border-radius: 50%;
    background: currentColor;
  }

  .legend-item.bullish {
    color: var(--mc-bullish);
  }
  .legend-item.bearish {
    color: var(--mc-bearish);
  }
  .legend-item.warning {
    color: var(--mc-warning);
  }
  .legend-item.accent {
    color: var(--mc-accent);
  }

  .scroll {
    overflow: auto;
    max-height: 32rem;
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
    position: sticky;
    top: 0;
    z-index: 1;
    padding: 0 var(--mc-space-3) var(--mc-space-2);
    text-align: left;
    font-size: var(--mc-text-xs);
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--mc-text-subtle);
    background: var(--mc-surface);
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
