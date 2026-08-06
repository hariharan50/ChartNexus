import { useRef, useState, type KeyboardEvent, type PointerEvent } from 'react';
import { cx } from '$shared/ui/cx';
import s from './TimeRangeSlider.module.css';

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

export default function TimeRangeSlider({
  min,
  max,
  openIndex,
  nowIndex,
  disabled = false,
  onOpenChange,
  onNowChange
}: Props) {
  const trackEl = useRef<HTMLDivElement>(null);
  const [dragging, setDragging] = useState<'open' | 'now' | null>(null);

  const span = Math.max(1, max - min);
  const openPct = ((openIndex - min) / span) * 100;
  const nowPct = ((nowIndex - min) / span) * 100;

  function indexFromClientX(clientX: number): number {
    const el = trackEl.current;
    if (!el) return min;
    const rect = el.getBoundingClientRect();
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

  function onPointerDown(event: PointerEvent<HTMLDivElement>) {
    if (disabled) return;
    // Whichever handle is nearer the click is the one being grabbed, so the
    // whole track is a valid target rather than just the ~20px thumb.
    const index = indexFromClientX(event.clientX);
    const which = Math.abs(index - openIndex) <= Math.abs(index - nowIndex) ? 'open' : 'now';
    setDragging(which);

    // Capture on the container, not the thumb: once captured every pointermove
    // arrives here even when the cursor leaves the element mid-drag.
    trackEl.current?.setPointerCapture?.(event.pointerId);
    event.preventDefault();
    moveHandle(which, event.clientX);
  }

  function onPointerMove(event: PointerEvent<HTMLDivElement>) {
    if (!dragging) return;
    event.preventDefault();
    moveHandle(dragging, event.clientX);
  }

  function onPointerUp(event: PointerEvent<HTMLDivElement>) {
    if (!dragging) return;
    trackEl.current?.releasePointerCapture?.(event.pointerId);
    setDragging(null);
  }

  function onKeyDown(which: 'open' | 'now', event: KeyboardEvent<HTMLDivElement>) {
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

  return (
    <div
      className={cx(s.track, disabled && s.disabled)}
      ref={trackEl}
      role="presentation"
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
    >
      <div className={s.rail} />
      <div className={s.fill} style={{ left: `${openPct}%`, right: `${100 - nowPct}%` }} />

      <div
        className={s.thumb}
        style={{ left: `${openPct}%` }}
        role="slider"
        aria-label="Window start"
        aria-valuemin={min}
        aria-valuemax={max}
        aria-valuenow={openIndex}
        aria-disabled={disabled}
        tabIndex={disabled ? -1 : 0}
        onKeyDown={(e) => onKeyDown('open', e)}
      />

      <div
        className={s.thumb}
        style={{ left: `${nowPct}%` }}
        role="slider"
        aria-label="Window end"
        aria-valuemin={min}
        aria-valuemax={max}
        aria-valuenow={nowIndex}
        aria-disabled={disabled}
        tabIndex={disabled ? -1 : 0}
        onKeyDown={(e) => onKeyDown('now', e)}
      />
    </div>
  );
}
