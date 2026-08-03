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
</script>

<Panel title="Option Chain" subtitle="Top strikes around spot">
  {#snippet icon()}<IconChart />{/snippet}
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
          {#each rows as row (row.strike + row.type)}
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
