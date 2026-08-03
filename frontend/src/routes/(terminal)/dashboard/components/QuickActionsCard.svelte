<script lang="ts">
  import type { Component } from 'svelte';
  import IconChart from '$shared/ui/icons/IconChart.svelte';
  import IconWallet from '$shared/ui/icons/IconWallet.svelte';
  import IconMessage from '$shared/ui/icons/IconMessage.svelte';
  import Panel from './Panel.svelte';

  interface Action {
    label: string;
    href: string;
    icon: Component;
  }

  const actions: Action[] = [
    { label: 'Options Chain', href: '/option-chain', icon: IconChart },
    { label: 'Smart Money', href: '/smart-insights', icon: IconWallet },
    { label: 'Ask Copilot', href: '/copilot', icon: IconMessage }
  ];
</script>

<Panel title="Quick Actions">
  {#snippet children()}
    <div class="actions">
      {#each actions as action (action.label)}
        {@const Icon = action.icon}
        <a class="action" href={action.href}>
          <span class="ico" aria-hidden="true"><Icon /></span>
          {action.label}
        </a>
      {/each}
    </div>
  {/snippet}
</Panel>

<style>
  .actions {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: var(--mc-space-2);
  }

  /* The third action spans the full width, matching the mockup. */
  .action:last-child:nth-child(odd) {
    grid-column: 1 / -1;
  }

  .action {
    display: inline-flex;
    align-items: center;
    gap: var(--mc-space-2);
    min-height: var(--mc-control-h);
    padding: 0 var(--mc-control-px);
    border: 1px solid var(--mc-border);
    border-radius: var(--mc-radius);
    background: var(--mc-surface-raised);
    color: var(--mc-text);
    font-size: var(--mc-text-sm);
    font-weight: 600;
    text-decoration: none;
    transition:
      border-color var(--mc-duration-fast) ease,
      background var(--mc-duration-fast) ease;
  }

  .action:hover {
    border-color: var(--mc-accent);
    background: var(--mc-accent-weak);
    text-decoration: none;
  }

  .ico {
    display: inline-flex;
    color: var(--mc-accent);
  }

  .ico :global(svg) {
    width: 1.05rem;
    height: 1.05rem;
  }
</style>
