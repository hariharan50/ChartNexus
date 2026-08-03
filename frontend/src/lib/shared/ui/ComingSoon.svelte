<script lang="ts">
  import IconClock from '$shared/ui/icons/IconClock.svelte';

  interface Props {
    title: string;
    description?: string;
  }

  let { title, description }: Props = $props();
</script>

<section class="coming-soon">
  <div class="panel">
    <span class="badge">
      <span class="badge-ico" aria-hidden="true"><IconClock /></span>
      Coming soon
    </span>
    <h1>{title}</h1>
    {#if description}
      <p>{description}</p>
    {/if}
  </div>
</section>

<style>
  .coming-soon {
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 70vh;
    padding: var(--mc-space-6);
  }

  .panel {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: var(--mc-space-3);
    max-width: 32rem;
    padding: var(--mc-space-8, 2.5rem) var(--mc-space-6);
    border: 1px solid var(--mc-border);
    border-radius: var(--mc-radius-lg, 0.75rem);
    background: var(--mc-surface);
    text-align: center;
  }

  .badge {
    display: inline-flex;
    align-items: center;
    gap: 0.375rem;
    padding: 0.25rem 0.625rem;
    border: 1px solid color-mix(in srgb, var(--mc-accent) 35%, transparent);
    border-radius: 999px;
    background: var(--mc-accent-weak);
    color: var(--mc-accent);
    font-size: var(--mc-text-xs);
    font-weight: 700;
    letter-spacing: 0.02em;
    text-transform: uppercase;
  }

  .badge-ico {
    display: inline-flex;
  }

  .badge-ico :global(svg) {
    width: 0.875rem;
    height: 0.875rem;
  }

  h1 {
    margin: 0;
    font-size: var(--mc-text-2xl, 1.5rem);
    font-weight: 700;
    letter-spacing: -0.02em;
    color: var(--mc-text);
  }

  p {
    margin: 0;
    font-size: var(--mc-text-sm);
    line-height: 1.5;
    color: var(--mc-text-muted);
  }
</style>
