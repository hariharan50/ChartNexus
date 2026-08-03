<script lang="ts">
  interface Props {
    callValue: number;
    putValue: number;
    callLabel: string;
    putLabel: string;
  }

  let { callValue, putValue, callLabel, putLabel }: Props = $props();

  // Heights normalise to the larger magnitude so the taller bar fills the box.
  const max = $derived(Math.max(1, Math.abs(callValue), Math.abs(putValue)));
  const callH = $derived(`${(Math.abs(callValue) / max) * 100}%`);
  const putH = $derived(`${(Math.abs(putValue) / max) * 100}%`);
</script>

<div class="pair">
  <div class="col">
    <span class="val call">{callLabel}</span>
    <div class="track"><div class="bar call" style="height: {callH}"></div></div>
    <span class="k">CALL</span>
  </div>
  <div class="col">
    <span class="val put">{putLabel}</span>
    <div class="track"><div class="bar put" style="height: {putH}"></div></div>
    <span class="k">PUT</span>
  </div>
</div>

<style>
  .pair {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: var(--mc-space-4);
    align-items: end;
  }

  .col {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.5rem;
  }

  .val {
    font-size: var(--mc-text-sm);
    font-weight: 700;
  }

  .val.call {
    color: var(--mc-bullish);
  }

  .val.put {
    color: var(--mc-bearish);
  }

  .track {
    display: flex;
    align-items: flex-end;
    height: 8rem;
    width: 3.5rem;
  }

  .bar {
    width: 100%;
    border-radius: var(--mc-radius-sm) var(--mc-radius-sm) 0 0;
    min-height: 2px;
  }

  .bar.call {
    background: var(--mc-bullish);
  }

  .bar.put {
    background: var(--mc-bearish);
  }

  .k {
    font-size: var(--mc-text-xs);
    font-weight: 600;
    letter-spacing: 0.06em;
    color: var(--mc-text-subtle);
  }
</style>
