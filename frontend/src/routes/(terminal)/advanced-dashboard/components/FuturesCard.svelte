<script lang="ts">
  import {
    formatPrice,
    formatSignedPercent,
    formatInt,
    direction
  } from '$shared/formatting/numbers';

  interface Props {
    label: string;
    /** Future last price; undefined renders a pending zero. */
    value?: number | undefined;
    changePercent?: number | undefined;
    volume?: number | undefined;
    contract?: string | undefined;
    dayHigh?: number | undefined;
    dayLow?: number | undefined;
  }

  let { label, value, changePercent, volume, contract, dayHigh, dayLow }: Props = $props();

  const dir = $derived(changePercent !== undefined ? direction(changePercent) : 'flat');
  const dash = (v: number | undefined) => (v != null ? formatPrice(v) : '—');
</script>

<div class="card">
  <div class="head">
    <span class="label">{label}</span>
    <span class="tag">FUT</span>
  </div>

  <span class="value mc-numeric">{value != null ? formatPrice(value) : '0.00'}</span>
  <span class="pill {dir}">{formatSignedPercent(changePercent ?? 0)}</span>

  <div class="grid">
    <div class="cell">
      <span class="k">Volume</span>
      <span class="v mc-numeric">{volume != null ? formatInt(volume) : '0'}</span>
    </div>
    <div class="cell">
      <span class="k">Contract</span>
      <span class="v contract">{contract ?? '—'}</span>
    </div>
    <div class="cell">
      <span class="k">Day High</span>
      <span class="v mc-numeric">{dash(dayHigh)}</span>
    </div>
    <div class="cell">
      <span class="k">Day Low</span>
      <span class="v mc-numeric">{dash(dayLow)}</span>
    </div>
  </div>

  <span class="accent" aria-hidden="true"></span>
</div>

<style>
  .card {
    position: relative;
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 0.5rem;
    padding: var(--mc-space-4) var(--mc-space-4) var(--mc-space-6);
    background: var(--mc-surface);
    border: 1px solid var(--mc-border);
    border-radius: var(--mc-radius-lg);
    box-shadow: var(--mc-shadow);
    overflow: hidden;
  }

  .head {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .label {
    font-size: var(--mc-text-xs);
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--mc-text-subtle);
  }

  .tag {
    padding: 0.0625rem 0.3125rem;
    border-radius: var(--mc-radius-sm);
    background: color-mix(in srgb, var(--mc-accent) 18%, transparent);
    color: var(--mc-accent);
    font-size: 0.625rem;
    font-weight: 700;
    letter-spacing: 0.04em;
  }

  .value {
    font-size: 2rem;
    font-weight: 700;
    letter-spacing: -0.02em;
    line-height: 1.05;
  }

  .pill {
    display: inline-flex;
    align-items: center;
    padding: 0.125rem 0.5rem;
    border-radius: 999px;
    font-size: var(--mc-text-xs);
    font-weight: 600;
  }

  .pill.up,
  .pill.flat {
    color: var(--mc-bullish);
    background: var(--mc-bullish-weak);
  }

  .pill.down {
    color: var(--mc-bearish);
    background: var(--mc-bearish-weak);
  }

  .grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: var(--mc-space-3) var(--mc-space-4);
    width: 100%;
    margin-top: var(--mc-space-2);
    padding-top: var(--mc-space-3);
    border-top: 1px solid var(--mc-border);
  }

  .cell {
    display: flex;
    flex-direction: column;
    gap: 0.1875rem;
    min-width: 0;
  }

  .k {
    font-size: var(--mc-text-xs);
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--mc-text-subtle);
  }

  .v {
    font-size: var(--mc-text-sm);
    font-weight: 600;
    color: var(--mc-text);
  }

  .v.contract {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .accent {
    position: absolute;
    left: 0;
    right: 0;
    bottom: 0;
    height: 3px;
    background: var(--mc-bullish);
  }
</style>
