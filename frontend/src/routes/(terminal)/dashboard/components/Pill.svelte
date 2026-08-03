<script lang="ts">
  import type { Snippet } from 'svelte';

  type Tone = 'bullish' | 'bearish' | 'warning' | 'accent' | 'neutral';

  interface Props {
    tone?: Tone;
    /** Softer, borderless treatment used for inline badges like ATM. */
    subtle?: boolean;
    children: Snippet;
  }

  let { tone = 'neutral', subtle = false, children }: Props = $props();
</script>

<span class="pill {tone}" class:subtle>{@render children()}</span>

<style>
  .pill {
    display: inline-flex;
    align-items: center;
    gap: 0.25rem;
    padding: 0.125rem 0.5rem;
    border: 1px solid transparent;
    border-radius: 999px;
    font-size: var(--mc-text-xs);
    font-weight: 600;
    line-height: 1.4;
    white-space: nowrap;
  }

  .bullish {
    color: var(--mc-bullish);
    background: color-mix(in srgb, var(--mc-bullish) 12%, transparent);
    border-color: color-mix(in srgb, var(--mc-bullish) 30%, transparent);
  }

  .bearish {
    color: var(--mc-bearish);
    background: color-mix(in srgb, var(--mc-bearish) 12%, transparent);
    border-color: color-mix(in srgb, var(--mc-bearish) 30%, transparent);
  }

  .warning {
    color: var(--mc-warning);
    background: color-mix(in srgb, var(--mc-warning) 14%, transparent);
    border-color: color-mix(in srgb, var(--mc-warning) 32%, transparent);
  }

  .accent {
    color: var(--mc-accent);
    background: color-mix(in srgb, var(--mc-accent) 14%, transparent);
    border-color: color-mix(in srgb, var(--mc-accent) 30%, transparent);
  }

  .neutral {
    color: var(--mc-text-muted);
    background: color-mix(in srgb, var(--mc-neutral) 14%, transparent);
    border-color: color-mix(in srgb, var(--mc-neutral) 26%, transparent);
  }

  .subtle {
    padding: 0.0625rem 0.3125rem;
    border-color: transparent;
    font-size: 0.625rem;
    letter-spacing: 0.03em;
  }
</style>
