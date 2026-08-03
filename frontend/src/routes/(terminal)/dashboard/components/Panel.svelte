<script lang="ts">
  import type { Snippet } from 'svelte';

  interface Props {
    /** Small leading icon rendered in the header. */
    icon?: Snippet;
    title?: string;
    subtitle?: string;
    /** Right-aligned header content (tabs, badges, actions). */
    actions?: Snippet;
    /** A coloured left accent bar — used by the AI summary panel. */
    accent?: boolean;
    padded?: boolean;
    children: Snippet;
  }

  let { icon, title, subtitle, actions, accent = false, padded = true, children }: Props = $props();

  const hasHeader = $derived(Boolean(icon || title || actions));
</script>

<section class="panel" class:accent>
  {#if hasHeader}
    <header class="panel-head">
      <div class="lead">
        {#if icon}
          <span class="icon" aria-hidden="true">{@render icon()}</span>
        {/if}
        {#if title}
          <div class="titles">
            <h2>{title}</h2>
            {#if subtitle}<p>{subtitle}</p>{/if}
          </div>
        {/if}
      </div>
      {#if actions}
        <div class="actions">{@render actions()}</div>
      {/if}
    </header>
  {/if}

  <div class="body" class:padded>{@render children()}</div>
</section>

<style>
  .panel {
    display: flex;
    flex-direction: column;
    background: var(--mc-surface);
    border: 1px solid var(--mc-border);
    border-radius: var(--mc-radius-lg);
    box-shadow: var(--mc-shadow);
    overflow: hidden;
  }

  .panel.accent {
    border-left: 3px solid var(--mc-accent);
  }

  .panel-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--mc-space-3);
    padding: var(--mc-space-4);
    border-bottom: 1px solid var(--mc-border);
  }

  .lead {
    display: flex;
    align-items: center;
    gap: var(--mc-space-3);
    min-width: 0;
  }

  .icon {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 1.75rem;
    height: 1.75rem;
    flex: none;
    border-radius: var(--mc-radius);
    background: var(--mc-accent-weak);
    color: var(--mc-accent);
  }

  .icon :global(svg) {
    width: 1.05rem;
    height: 1.05rem;
  }

  .titles {
    min-width: 0;
  }

  h2 {
    margin: 0;
    font-size: var(--mc-text-base);
    font-weight: 700;
    letter-spacing: -0.01em;
  }

  .titles p {
    margin: 0.0625rem 0 0;
    font-size: var(--mc-text-xs);
    color: var(--mc-text-subtle);
  }

  .actions {
    display: flex;
    align-items: center;
    gap: var(--mc-space-2);
    flex: none;
  }

  .body.padded {
    padding: var(--mc-space-4);
  }
</style>
