<script lang="ts">
  interface Props {
    /** Local clock string, e.g. "10:46:46 IST". */
    time: string;
    live?: boolean;
  }

  let { time, live = true }: Props = $props();
</script>

<span class="badge" class:live>
  <span class="dot" aria-hidden="true"></span>
  {live ? 'Live' : 'Delayed'} — {time}
</span>

<style>
  .badge {
    display: inline-flex;
    align-items: center;
    gap: 0.4375rem;
    padding: 0.375rem 0.75rem;
    border: 1px solid var(--mc-border);
    border-radius: 999px;
    background: var(--mc-surface);
    box-shadow: var(--mc-shadow);
    font-size: var(--mc-text-xs);
    font-weight: 600;
    color: var(--mc-text-muted);
    white-space: nowrap;
  }

  .dot {
    width: 0.5rem;
    height: 0.5rem;
    border-radius: 50%;
    background: var(--mc-stale);
  }

  .live .dot {
    background: var(--mc-live);
    box-shadow: 0 0 0 3px color-mix(in srgb, var(--mc-live) 22%, transparent);
    animation: pulse 2s ease-in-out infinite;
  }

  @keyframes pulse {
    50% {
      opacity: 0.55;
    }
  }
</style>
