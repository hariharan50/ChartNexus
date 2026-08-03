<script lang="ts">
  import { CALL_COLOR, PUT_COLOR } from '../oi-data';

  interface Props {
    pcr: number;
    callNow: number;
    putNow: number;
  }

  let { pcr, callNow, putNow }: Props = $props();

  const total = $derived(Math.max(1, callNow + putNow));
  const callPct = $derived(Math.round((callNow / total) * 100));
  const putPct = $derived(100 - callPct);

  const R = 58;
  const CIRC = 2 * Math.PI * R;
  // Green arc = call share, drawn over the full red ring.
  const dash = $derived(`${(callPct / 100) * CIRC} ${CIRC}`);
</script>

<div class="wrap">
  <span class="side call">{callPct}% Call OI</span>
  <div class="donut">
    <svg viewBox="0 0 140 140" width="140" height="140" class="ring" aria-hidden="true">
      <circle cx="70" cy="70" r={R} fill="none" stroke={PUT_COLOR} stroke-width="14" />
      <circle
        cx="70"
        cy="70"
        r={R}
        fill="none"
        stroke={CALL_COLOR}
        stroke-width="14"
        stroke-dasharray={dash}
      />
    </svg>
    <div class="center">
      <span class="k">PCR</span>
      <span class="v">{pcr.toFixed(2)}</span>
    </div>
  </div>
  <span class="side put">{putPct}% Put OI</span>
</div>

<style>
  .wrap {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: var(--mc-space-3);
  }

  .donut {
    position: relative;
    width: 140px;
    height: 140px;
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
  }

  .k {
    font-size: var(--mc-text-xs);
    color: var(--mc-text-subtle);
  }

  .v {
    font-size: var(--mc-text-xl);
    font-weight: 700;
    color: var(--mc-text);
  }

  .side {
    font-size: var(--mc-text-xs);
    font-weight: 700;
    max-width: 3rem;
    line-height: 1.2;
  }

  .side.call {
    color: var(--mc-bullish);
    text-align: right;
  }

  .side.put {
    color: var(--mc-bearish);
  }
</style>
