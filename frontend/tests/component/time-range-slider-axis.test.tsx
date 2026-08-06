import { render } from '@testing-library/react';
import { act } from 'react';
import { beforeAll, describe, expect, it, vi } from 'vitest';
import TimeRangeSlider from '../../app/routes/terminal/options/open-interest/components/TimeRangeSlider';
import type { SliderTick } from '../../app/routes/terminal/options/open-interest/oi-data';

/**
 * The time axis and per-handle readout added on top of the drag gesture.
 *
 * `time-range-slider.test.tsx` is the regression gate for the gesture itself and
 * is deliberately untouched; this file covers only what the wrapper added. The
 * one overlapping assertion is the last test here, and it is the important one:
 * the bubble is wider than the thumb and sits exactly where you reach to grab,
 * so if it ever takes a hit-test the slider stops dragging.
 */

const TRACK_LEFT = 100;
const TRACK_WIDTH = 400;

beforeAll(() => {
  Element.prototype.getBoundingClientRect = vi.fn(
    () =>
      ({
        left: TRACK_LEFT,
        right: TRACK_LEFT + TRACK_WIDTH,
        width: TRACK_WIDTH,
        top: 0,
        bottom: 28,
        height: 28,
        x: TRACK_LEFT,
        y: 0,
        toJSON: () => ({})
      }) as DOMRect
  );
  Element.prototype.setPointerCapture = vi.fn();
  Element.prototype.releasePointerCapture = vi.fn();
});

const TICKS: SliderTick[] = [
  { index: 0, pct: 0, label: '9 am' },
  { index: 15, pct: 25, label: null },
  { index: 30, pct: 50, label: '10 am' },
  { index: 60, pct: 100, label: '11 am' }
];

interface Props {
  openIndex?: number;
  nowIndex?: number;
  openLabel?: string;
  nowLabel?: string;
  ticks?: SliderTick[];
  disabled?: boolean;
}

function setup(props: Props = {}) {
  const onOpenChange = vi.fn();
  const onNowChange = vi.fn();
  const { container } = render(
    <TimeRangeSlider
      min={0}
      max={60}
      openIndex={0}
      nowIndex={60}
      openLabel="9:15 am"
      nowLabel="3:30 pm"
      ticks={TICKS}
      onOpenChange={onOpenChange}
      onNowChange={onNowChange}
      {...props}
    />
  );
  const track = container.querySelector('[role="presentation"]') as HTMLElement;
  const thumbs = [...track.querySelectorAll('[role="slider"]')] as HTMLElement[];
  return { container, track, thumbs, onOpenChange, onNowChange };
}

function pointer(type: string, clientX: number) {
  const event = new MouseEvent(type, { bubbles: true, cancelable: true, clientX });
  Object.defineProperty(event, 'pointerId', { value: 1 });
  return event;
}

function fire(target: HTMLElement, event: Event) {
  act(() => {
    target.dispatchEvent(event);
  });
}

describe('TimeRangeSlider axis', () => {
  it('renders one mark per tick, positioned where it was told', () => {
    const { container } = setup();
    const axis = container.querySelector('[aria-hidden="true"]') as HTMLElement;
    const marks = [...axis.children] as HTMLElement[];

    expect(marks).toHaveLength(4);
    expect(marks.map((m) => m.style.left)).toEqual(['0%', '25%', '50%', '100%']);
  });

  it('shows the hour labels and leaves the half hours bare', () => {
    const { container } = setup();
    const axis = container.querySelector('[aria-hidden="true"]') as HTMLElement;

    expect(axis.textContent).toBe('9 am10 am11 am');
  });

  it('hides the axis from assistive technology', () => {
    // The times are already on the handles as `aria-valuetext`; reading a row of
    // decorative marks as well would be noise.
    const { container, track } = setup();
    const axis = container.querySelector('[aria-hidden="true"]') as HTMLElement;

    expect(axis).not.toBeNull();
    expect(track.contains(axis)).toBe(false);
  });

  it('keeps the axis out of the track so it cannot join the drag region', () => {
    const { container, track } = setup();
    const axis = container.querySelector('[aria-hidden="true"]') as HTMLElement;

    expect(axis.parentElement).toBe(track.parentElement);
  });

  it('renders nothing when there are no ticks', () => {
    const { container } = setup({ ticks: [] });
    const axis = container.querySelector('[aria-hidden="true"]') as HTMLElement;

    expect(axis.children).toHaveLength(0);
  });
});

describe('TimeRangeSlider readout', () => {
  it('shows each handle its own clock reading', () => {
    const { thumbs } = setup();

    expect(thumbs[0]!.textContent).toBe('9:15 am');
    expect(thumbs[1]!.textContent).toBe('3:30 pm');
  });

  it('announces the time, not the frame number', () => {
    // `aria-valuenow` is a frame index, which means nothing to a listener.
    const { thumbs } = setup();

    expect(thumbs[0]!.getAttribute('aria-valuetext')).toBe('9:15 am');
    expect(thumbs[0]!.getAttribute('aria-label')).toBe('Baseline time');
    expect(thumbs[1]!.getAttribute('aria-valuetext')).toBe('3:30 pm');
    expect(thumbs[1]!.getAttribute('aria-label')).toBe('As-of time');
  });

  it('omits the bubble when there is no time to show', () => {
    // Rendered without the label props at all — under `exactOptionalPropertyTypes`
    // an explicit `undefined` is not the same as an absent key, and absent is
    // what "the parent has no time yet" means.
    const { container } = render(
      <TimeRangeSlider
        min={0}
        max={60}
        openIndex={0}
        nowIndex={60}
        ticks={TICKS}
        onOpenChange={vi.fn()}
        onNowChange={vi.fn()}
      />
    );
    const thumb = container.querySelectorAll('[role="slider"]')[0] as HTMLElement;

    expect(thumb.textContent).toBe('');
  });

  it('a press that lands on a bubble still drags the handle', () => {
    // The regression this guards: a child of the thumb taking the hit-test.
    // Dispatching from the bubble reproduces exactly that — the event's target
    // is the bubble, and it must still bubble to the track's handler.
    const { thumbs, onNowChange } = setup();
    const bubble = thumbs[1]!.firstElementChild as HTMLElement;

    expect(bubble).not.toBeNull();
    fire(bubble, pointer('pointerdown', TRACK_LEFT + TRACK_WIDTH * 0.75));

    expect(onNowChange).toHaveBeenCalledWith(45);
  });
});

describe('TimeRangeSlider keyboard paging', () => {
  it('jumps ten frames with PageUp and PageDown', () => {
    const { thumbs, onNowChange } = setup({ openIndex: 0, nowIndex: 40 });

    fire(
      thumbs[1]!,
      new KeyboardEvent('keydown', { key: 'PageDown', bubbles: true, cancelable: true })
    );
    fire(
      thumbs[1]!,
      new KeyboardEvent('keydown', { key: 'PageUp', bubbles: true, cancelable: true })
    );

    expect(onNowChange).toHaveBeenNthCalledWith(1, 30);
    expect(onNowChange).toHaveBeenNthCalledWith(2, 50);
  });

  it('clamps paging to the ends of the track', () => {
    const { thumbs, onOpenChange } = setup({ openIndex: 3, nowIndex: 60 });

    fire(
      thumbs[0]!,
      new KeyboardEvent('keydown', { key: 'PageDown', bubbles: true, cancelable: true })
    );

    expect(onOpenChange).toHaveBeenCalledWith(0);
  });
});

describe('TimeRangeSlider drag throttling', () => {
  it('does not re-report a position the drag is already on', () => {
    // `indexFromClientX` rounds, so a slow drag across one frame's width fires
    // dozens of pointermoves that all resolve to the same index. Each one used
    // to cost a parent re-render and an ECharts `setOption`.
    const { track, onOpenChange } = setup();
    const x = TRACK_LEFT + TRACK_WIDTH * 0.25;

    fire(track, pointer('pointerdown', x));
    fire(track, pointer('pointermove', x + 1));
    fire(track, pointer('pointermove', x + 2));
    fire(track, pointer('pointermove', x + 1));

    expect(onOpenChange).toHaveBeenCalledTimes(1);
    expect(onOpenChange).toHaveBeenCalledWith(15);
  });

  it('still reports every genuine change', () => {
    const { track, onOpenChange } = setup();

    fire(track, pointer('pointerdown', TRACK_LEFT + TRACK_WIDTH * 0.25));
    fire(track, pointer('pointermove', TRACK_LEFT + TRACK_WIDTH * 0.5));
    fire(track, pointer('pointermove', TRACK_LEFT + TRACK_WIDTH * 0.25));

    expect(onOpenChange.mock.calls.map((c) => c[0])).toEqual([15, 30, 15]);
  });

  it('forgets the last position between drags', () => {
    // Otherwise pressing twice in the same spot would silently do nothing the
    // second time — and the parent may not have accepted the first.
    const { track, onOpenChange } = setup();
    const x = TRACK_LEFT + TRACK_WIDTH * 0.25;

    fire(track, pointer('pointerdown', x));
    fire(track, pointer('pointerup', x));
    fire(track, pointer('pointerdown', x));

    expect(onOpenChange).toHaveBeenCalledTimes(2);
  });
});
