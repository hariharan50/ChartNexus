<script lang="ts">
  import type { IndexKey } from '../dashboard-data';

  interface Props {
    value: IndexKey;
    onchange?: (key: IndexKey) => void;
  }

  let { value, onchange }: Props = $props();

  const tabs: { key: IndexKey; label: string }[] = [
    { key: 'NIFTY50', label: 'NIFTY 50' },
    { key: 'SENSEX', label: 'SENSEX' },
    { key: 'BANKNIFTY', label: 'BANK NIFTY' }
  ];
</script>

<div class="tabs" role="tablist" aria-label="Focused index">
  {#each tabs as tab (tab.key)}
    <button
      type="button"
      role="tab"
      class="tab"
      class:active={value === tab.key}
      aria-selected={value === tab.key}
      onclick={() => onchange?.(tab.key)}
    >
      {tab.label}
    </button>
  {/each}
</div>

<style>
  .tabs {
    display: inline-flex;
    padding: 0.1875rem;
    gap: 0.125rem;
    background: var(--mc-surface-raised);
    border: 1px solid var(--mc-border);
    border-radius: var(--mc-radius);
  }

  .tab {
    padding: 0.3125rem 0.75rem;
    border: none;
    border-radius: var(--mc-radius-sm);
    background: transparent;
    color: var(--mc-text-muted);
    font-size: var(--mc-text-xs);
    font-weight: 700;
    letter-spacing: 0.02em;
    cursor: pointer;
    transition:
      background var(--mc-duration-fast) ease,
      color var(--mc-duration-fast) ease;
  }

  .tab:hover {
    color: var(--mc-text);
  }

  .tab.active {
    background: var(--mc-accent);
    color: #fff;
  }
</style>
