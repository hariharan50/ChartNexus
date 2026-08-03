<script lang="ts">
  import type { Side } from '../chain-model';

  interface Props {
    value?: number | undefined;
    max: number;
    side: Side;
  }

  let { value, max, side }: Props = $props();

  // Calls fill from the right (reading inward toward the strike), puts from the
  // left. Clamp so a rounding overshoot never spills past the track.
  const pct = $derived(value != null && max > 0 ? Math.min(100, (value / max) * 100) : 0);
</script>

<span class="track">
  <span class="fill {side}" style="width: {pct}%"></span>
</span>

<style>
  .track {
    display: block;
    position: relative;
    height: 0.375rem;
    width: 5rem;
    border-radius: 999px;
    background: var(--mc-border);
  }

  .fill {
    position: absolute;
    top: 0;
    height: 100%;
    border-radius: 999px;
  }

  .fill.ce {
    right: 0;
    background: var(--mc-bullish);
  }

  .fill.pe {
    left: 0;
    background: var(--mc-bearish);
  }
</style>
