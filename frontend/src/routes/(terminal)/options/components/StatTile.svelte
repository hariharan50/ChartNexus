<script lang="ts">
  import type { Snippet } from 'svelte';
  import Pill from '../../dashboard/components/Pill.svelte';

  type Tone = 'bullish' | 'bearish' | 'warning' | 'accent' | 'neutral';

  interface Props {
    label: string;
    value: string;
    /** Small muted line under the value (e.g. "Neutral"). */
    sub?: string | undefined;
    /** A pill rendered under the value (e.g. "Dominant"). */
    pill?: string | undefined;
    pillTone?: Tone;
    /** Accent the value colour for support/resistance style tiles. */
    valueTone?: 'bullish' | 'bearish' | undefined;
    /** Optional custom footer, overrides sub/pill when provided. */
    footer?: Snippet | undefined;
  }

  let { label, value, sub, pill, pillTone = 'neutral', valueTone, footer }: Props = $props();
</script>

<div class="tile">
  <p class="label">{label}</p>
  <p
    class="value mc-numeric"
    class:bullish={valueTone === 'bullish'}
    class:bearish={valueTone === 'bearish'}
  >
    {value}
  </p>
  {#if footer}
    <div class="footer">{@render footer()}</div>
  {:else if pill}
    <div class="footer"><Pill tone={pillTone} subtle>{pill}</Pill></div>
  {:else if sub}
    <p class="sub">{sub}</p>
  {/if}
</div>

<style>
  .tile {
    display: flex;
    flex-direction: column;
    padding: var(--mc-space-4);
    background: var(--mc-surface);
    border: 1px solid var(--mc-border);
    border-radius: var(--mc-radius-lg);
    box-shadow: var(--mc-shadow);
    min-width: 0;
  }

  .label {
    margin: 0;
    font-size: var(--mc-text-xs);
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--mc-text-subtle);
  }

  .value {
    margin: var(--mc-space-2) 0 0;
    font-size: var(--mc-text-2xl);
    font-weight: 700;
    letter-spacing: -0.02em;
    color: var(--mc-text);
  }

  .value.bullish {
    color: var(--mc-bullish);
  }

  .value.bearish {
    color: var(--mc-bearish);
  }

  .sub {
    margin: var(--mc-space-2) 0 0;
    font-size: var(--mc-text-sm);
    color: var(--mc-text-muted);
  }

  .footer {
    margin-top: var(--mc-space-2);
  }
</style>
