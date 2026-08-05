<script lang="ts">
  /**
   * A two-handle range slider for scrubbing the OI session window.
   *
   * The container owns the entire gesture: on pointer-down it captures the
   * pointer, so every subsequent move lands here regardless of what is under
   * the cursor. The thumbs are inert (`pointer-events: none`) and exist only to
   * be seen and to carry keyboard focus — nothing competes for the drag.
   *
   * The previous implementation leaned on `pointer-events: auto` applied to
   * `::-webkit-slider-thumb` over a `pointer-events: none` input. That is a
   * commonly-cited trick but an unreliable one: the browser hit-tests the input
   * element before the pseudo-element, so grabbing the thumb frequently did
   * nothing at all.
   */
  interface Props {
    min: number;
    max: number;
    openIndex: number;
    nowIndex: number;
    disabled?: boolean;
    onOpenChange: (index: number) => void;
    onNowChange: (index: number) => void;
  }

  let {
    min,
    max,
    openIndex,
    nowIndex,
    disabled = false,
    onOpenChange,
    onNowChange
  }: Props = $props();

  let trackEl: HTMLDivElement | undefined = $state();
  let dragging: 'open' | 'now' | null = $state(null);

  const span = $derived(Math.max(1, max - min));
  const openPct = $derived(((openIndex - min) / span) * 100);
  const nowPct = $derived(((nowIndex - min) / span) * 100);

  function indexFromClientX(clientX: number): number {
    if (!trackEl) return min;
    const rect = trackEl.getBoundingClientRect();
    if (rect.width <= 0) return min;
    const ratio = (clientX - rect.left) / rect.width;
    const index = Math.round(ratio * span) + min;
    return Math.min(max, Math.max(min, index));
  }

  /** Move a handle, keeping the two from crossing over each other. */
  function moveHandle(which: 'open' | 'now', clientX: number) {
    const index = indexFromClientX(clientX);
    if (which === 'open') onOpenChange(Math.min(index, nowIndex));
    else onNowChange(Math.max(index, openIndex));
  }

  function onPointerDown(event: PointerEvent) {
    if (disabled) return;
    // Whichever handle is nearer the click is the one being grabbed, so the
    // whole track is a valid target rather than just the ~20px thumb.
    const index = indexFromClientX(event.clientX);
    dragging = Math.abs(index - openIndex) <= Math.abs(index - nowIndex) ? 'open' : 'now';

    // Capture on the container, not the thumb: once captured every pointermove
    // arrives here even when the cursor leaves the element mid-drag.
    trackEl?.setPointerCapture?.(event.pointerId);
    event.preventDefault();
    moveHandle(dragging, event.clientX);
  }

  function onPointerMove(event: PointerEvent) {
    if (!dragging) return;
    event.preventDefault();
    moveHandle(dragging, event.clientX);
  }

  function onPointerUp(event: PointerEvent) {
    if (!dragging) return;
    trackEl?.releasePointerCapture?.(event.pointerId);
    dragging = null;
  }

  function onKeydown(which: 'open' | 'now', event: KeyboardEvent) {
    if (disabled) return;
    const current = which === 'open' ? openIndex : nowIndex;
    let next: number | undefined;
    if (event.key === 'ArrowLeft' || event.key === 'ArrowDown') next = current - 1;
    else if (event.key === 'ArrowRight' || event.key === 'ArrowUp') next = current + 1;
    else if (event.key === 'Home') next = min;
    else if (event.key === 'End') next = max;
    if (next === undefined) return;

    event.preventDefault();
    next = Math.min(max, Math.max(min, next));
    if (which === 'open') onOpenChange(Math.min(next, nowIndex));
    else onNowChange(Math.max(next, openIndex));
  }
</script>

<div
  class="track"
  class:disabled
  bind:this={trackEl}
  role="presentation"
  onpointerdown={onPointerDown}
  onpointermove={onPointerMove}
  onpointerup={onPointerUp}
  onpointercancel={onPointerUp}
>
  <div class="rail"></div>
  <div class="fill" style="left:{openPct}%; right:{100 - nowPct}%"></div>

  <div
    class="thumb"
    style="left:{openPct}%"
    role="slider"
    aria-label="Window start"
    aria-valuemin={min}
    aria-valuemax={max}
    aria-valuenow={openIndex}
    aria-disabled={disabled}
    tabindex={disabled ? -1 : 0}
    onkeydown={(e) => onKeydown('open', e)}
  ></div>

  <div
    class="thumb"
    style="left:{nowPct}%"
    role="slider"
    aria-label="Window end"
    aria-valuemin={min}
    aria-valuemax={max}
    aria-valuenow={nowIndex}
    aria-disabled={disabled}
    tabindex={disabled ? -1 : 0}
    onkeydown={(e) => onKeydown('now', e)}
  ></div>
</div>

<style>
  .track {
    position: relative;
    flex: 1;
    height: 1.75rem;
    display: flex;
    align-items: center;
    /* Without this a drag on touch scrolls the page instead of moving a handle. */
    touch-action: none;
    cursor: pointer;
  }

  .track.disabled {
    opacity: 0.5;
    cursor: default;
  }

  .rail {
    position: absolute;
    left: 0;
    right: 0;
    height: 0.25rem;
    border-radius: 999px;
    background: var(--mc-border-strong);
  }

  .fill {
    position: absolute;
    height: 0.25rem;
    border-radius: 999px;
    background: var(--mc-bearish);
  }

  /* Inert by design — the container handles every pointer gesture, so a thumb
     must never become the event target and swallow it. */
  .thumb {
    position: absolute;
    top: 50%;
    width: 1.375rem;
    height: 1.375rem;
    border-radius: 50%;
    border: 2px solid var(--mc-bearish);
    background: var(--mc-surface);
    box-shadow: 0 1px 3px rgb(0 0 0 / 0.35);
    transform: translate(-50%, -50%);
    pointer-events: none;
  }

  .track:not(.disabled) .thumb:focus-visible {
    outline: 2px solid var(--mc-bearish);
    outline-offset: 2px;
  }
</style>
