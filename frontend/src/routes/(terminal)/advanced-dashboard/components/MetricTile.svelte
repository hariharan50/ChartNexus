<script lang="ts">
  interface Props {
    label: string;
    value: string;
    tone?: 'default' | 'bullish' | 'bearish' | 'warning' | 'accent';
  }

  let { label, value, tone = 'default' }: Props = $props();
</script>

<div class="tile">
  <span class="label">{label}</span>
  <span class="value mc-numeric {tone}">{value}</span>
</div>

<style>
  .tile {
    display: flex;
    flex-direction: column;
    gap: 0.375rem;
    padding: var(--mc-space-4);
    background: var(--mc-surface);
    border: 1px solid var(--mc-border);
    border-radius: var(--mc-radius-lg);
    box-shadow: var(--mc-shadow);
  }

  .label {
    font-size: var(--mc-text-xs);
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--mc-text-subtle);
  }

  .value {
    font-size: 1.75rem;
    font-weight: 700;
    letter-spacing: -0.02em;
    line-height: 1.05;
    color: var(--mc-text);
  }

  .value.bullish {
    color: var(--mc-bullish);
  }

  .value.bearish {
    color: var(--mc-bearish);
  }

  .value.warning {
    color: var(--mc-warning);
  }

  .value.accent {
    color: var(--mc-accent);
  }
</style>
