<script lang="ts">
  interface Props {
    label: string;
    percent: number;
  }

  let { label, percent }: Props = $props();

  const R = 58;
  const CIRC = 2 * Math.PI * R;
  const color = $derived(
    label === 'Bullish' ? '#16a34a' : label === 'Bearish' ? '#ef4444' : '#f59e0b'
  );
  const dash = $derived(`${(Math.min(100, Math.max(0, percent)) / 100) * CIRC} ${CIRC}`);
</script>

<div class="donut">
  <svg viewBox="0 0 140 140" width="140" height="140" class="ring" aria-hidden="true">
    <circle cx="70" cy="70" r={R} fill="none" stroke="var(--mc-border)" stroke-width="14" />
    <circle
      cx="70"
      cy="70"
      r={R}
      fill="none"
      stroke={color}
      stroke-width="14"
      stroke-linecap="round"
      stroke-dasharray={dash}
    />
  </svg>
  <div class="center">
    <span class="label" style="color: {color}">{label}</span>
    <span class="sub">{label} market conditions</span>
    <span class="pct">{percent}%</span>
  </div>
</div>

<style>
  .donut {
    position: relative;
    width: 140px;
    height: 140px;
    margin: 0 auto;
  }

  .ring {
    transform: rotate(-90deg);
  }

  .center {
    position: absolute;
    inset: 0;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    text-align: center;
    gap: 0.125rem;
  }

  .label {
    font-size: var(--mc-text-lg);
    font-weight: 700;
  }

  .sub {
    font-size: 0.5625rem;
    color: var(--mc-text-subtle);
    max-width: 5rem;
    line-height: 1.2;
  }

  .pct {
    margin-top: 0.125rem;
    font-size: var(--mc-text-lg);
    font-weight: 700;
    color: var(--mc-text);
  }
</style>
