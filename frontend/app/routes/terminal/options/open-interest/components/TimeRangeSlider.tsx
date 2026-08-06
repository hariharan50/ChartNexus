import { useRef, useState, type KeyboardEvent, type PointerEvent } from 'react';
import { cx } from '$shared/ui/cx';
import type { SliderTick } from '../oi-data';
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
 *
 * It is a purely positional widget: it knows about frame *indices*, never about
 * time. The times it shows are handed to it, and the tick positions are computed
 * by the caller from the same index space the handles move in.
 */
interface Props {
  min: number;
  max: number;
  openIndex: number;
  nowIndex: number;
  disabled?: boolean;
  /** IST clock reading at each handle, e.g. `10:30 am`. */
  openLabel?: string;
  nowLabel?: string;
  /** Hour / half-hour marks under the track. */
  ticks?: SliderTick[];
  onOpenChange: (index: number) => void;
  onNowChange: (index: number) => void;
}

/** PageUp/PageDown jump ten frames — half an hour at the 3-minute cadence. */
const PAGE_STEP = 10;

export default function TimeRangeSlider({
  min,
  max,
  openIndex,
  nowIndex,
  disabled = false,
  openLabel,
  nowLabel,
  ticks = [],
  onOpenChange,
  onNowChange
}: Props) {
  const trackEl = useRef<HTMLDivElement>(null);
  const [dragging, setDragging] = useState<'open' | 'now' | null>(null);
  /**
   * The last index this drag emitted.
   *
   * `indexFromClientX` rounds, so a slow drag across one frame's width produces
   * dozens of pointermoves that all resolve to the same index; without this the
   * parent re-renders and ECharts calls `setOption` for every one of them.
   * Compared against what we *sent*, not against the prop — the parent is free
   * not to accept a value, and a rejected move must still be retried.
   */
  const lastSent = useRef<number | null>(null);

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
    const next = which === 'open' ? Math.min(index, nowIndex) : Math.max(index, openIndex);
    if (lastSent.current === next) return;
    lastSent.current = next;
    if (which === 'open') onOpenChange(next);
    else onNowChange(next);
  }

  function onPointerDown(event: PointerEvent<HTMLDivElement>) {
    if (disabled) return;
    // Whichever handle is nearer the click is the one being grabbed, so the
    // whole track is a valid target rather than just the ~20px thumb.
    const index = indexFromClientX(event.clientX);
    const which = Math.abs(index - openIndex) <= Math.abs(index - nowIndex) ? 'open' : 'now';
    setDragging(which);
    lastSent.current = null;

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
    lastSent.current = null;
  }

  function onKeyDown(which: 'open' | 'now', event: KeyboardEvent<HTMLDivElement>) {
    if (disabled) return;
    const current = which === 'open' ? openIndex : nowIndex;
    let next: number | undefined;
    if (event.key === 'ArrowLeft' || event.key === 'ArrowDown') next = current - 1;
    else if (event.key === 'ArrowRight' || event.key === 'ArrowUp') next = current + 1;
    else if (event.key === 'PageDown') next = current - PAGE_STEP;
    else if (event.key === 'PageUp') next = current + PAGE_STEP;
    else if (event.key === 'Home') next = min;
    else if (event.key === 'End') next = max;
    if (next === undefined) return;

    event.preventDefault();
    next = Math.min(max, Math.max(min, next));
    if (which === 'open') onOpenChange(Math.min(next, nowIndex));
    else onNowChange(Math.max(next, openIndex));
  }

  return (
    <div className={s.root}>
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
          aria-label="Baseline time"
          aria-valuemin={min}
          aria-valuemax={max}
          aria-valuenow={openIndex}
          aria-valuetext={openLabel}
          aria-disabled={disabled}
          tabIndex={disabled ? -1 : 0}
          onKeyDown={(e) => onKeyDown('open', e)}
        >
          {openLabel ? (
            <span className={cx(s.bubble, dragging === 'open' && s.active)}>{openLabel}</span>
          ) : null}
        </div>

        <div
          className={s.thumb}
          style={{ left: `${nowPct}%` }}
          role="slider"
          aria-label="As-of time"
          aria-valuemin={min}
          aria-valuemax={max}
          aria-valuenow={nowIndex}
          aria-valuetext={nowLabel}
          aria-disabled={disabled}
          tabIndex={disabled ? -1 : 0}
          onKeyDown={(e) => onKeyDown('now', e)}
        >
          {nowLabel ? (
            <span className={cx(s.bubble, dragging === 'now' && s.active)}>{nowLabel}</span>
          ) : null}
        </div>
      </div>

      {/* A sibling of the track, never a child: inside it the axis would sit in
          the pointer-capture region and become part of the drag target. */}
      <div className={s.axis} aria-hidden="true">
        {ticks.map((tick) => (
          <span
            key={tick.index}
            className={cx(s.tick, tick.label && s.major)}
            style={{ left: `${tick.pct}%` }}
          >
            {tick.label ? <span className={s.tickLabel}>{tick.label}</span> : null}
          </span>
        ))}
      </div>
    </div>
  );
}
