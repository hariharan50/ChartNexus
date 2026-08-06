import { render } from '@testing-library/react';
import { act } from 'react';
import { beforeAll, describe, expect, it, vi } from 'vitest';
import TimeRangeSlider from '../../app/routes/terminal/options/components/TimeRangeSlider';

/**
 * Proves the drag gesture actually reaches the callbacks.
 *
 * This exists because three separate implementations "looked correct" and none
 * of them moved in a real browser — the bug was always in how the pointer
 * gesture was wired, which is exactly what these assertions pin down.
 *
 * Ported from the Svelte suite with every case and expected value unchanged, so
 * a behaviour change in the port would show up here rather than in production.
 * Only the mechanics differ: the component is found by ARIA role instead of by
 * class name, because CSS Modules hashes the class.
 */

const TRACK_LEFT = 100;
const TRACK_WIDTH = 400;

beforeAll(() => {
  // jsdom lays nothing out, so the track would measure 0x0 and every computed
  // index would collapse to `min`.
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
  // Pointer capture is not implemented in jsdom; the component calls it
  // optionally, but stub it so the calls are observable rather than skipped.
  Element.prototype.setPointerCapture = vi.fn();
  Element.prototype.releasePointerCapture = vi.fn();
});

/** clientX for a given fraction along the track. */
const atFraction = (fraction: number) => TRACK_LEFT + TRACK_WIDTH * fraction;

function pointer(type: string, clientX: number) {
  // jsdom has no PointerEvent constructor, so build a MouseEvent and attach the
  // two pointer fields the component reads.
  const event = new MouseEvent(type, { bubbles: true, cancelable: true, clientX });
  Object.defineProperty(event, 'pointerId', { value: 1 });
  return event;
}

/** React batches inside `act`, so state written by one event is visible to the next. */
function fire(target: HTMLElement, event: Event) {
  act(() => {
    target.dispatchEvent(event);
  });
}

interface Props {
  min?: number;
  max?: number;
  openIndex?: number;
  nowIndex?: number;
  disabled?: boolean;
}

function setup(props: Props = {}) {
  const onOpenChange = vi.fn();
  const onNowChange = vi.fn();
  const { container } = render(
    <TimeRangeSlider
      min={0}
      max={100}
      openIndex={0}
      nowIndex={100}
      onOpenChange={onOpenChange}
      onNowChange={onNowChange}
      {...props}
    />
  );
  const track = container.querySelector('[role="presentation"]') as HTMLElement;
  return { track, onOpenChange, onNowChange };
}

describe('TimeRangeSlider', () => {
  it('grabs the nearer handle and reports the dragged position', () => {
    const { track, onOpenChange, onNowChange } = setup();

    // A quarter along the track is nearest the start handle (at 0).
    fire(track, pointer('pointerdown', atFraction(0.25)));

    expect(onOpenChange).toHaveBeenCalledWith(25);
    expect(onNowChange).not.toHaveBeenCalled();
  });

  it('keeps following the pointer after the initial press', () => {
    const { track, onOpenChange } = setup();

    fire(track, pointer('pointerdown', atFraction(0.1)));
    fire(track, pointer('pointermove', atFraction(0.3)));
    fire(track, pointer('pointermove', atFraction(0.4)));

    // The whole point: a drag is a sequence, not a single click.
    expect(onOpenChange).toHaveBeenLastCalledWith(40);
    expect(onOpenChange).toHaveBeenCalledTimes(3);
  });

  it('drags the end handle when the press is nearer to it', () => {
    const { track, onNowChange, onOpenChange } = setup();

    fire(track, pointer('pointerdown', atFraction(0.9)));

    expect(onNowChange).toHaveBeenCalledWith(90);
    expect(onOpenChange).not.toHaveBeenCalled();
  });

  it('stops responding once the pointer is released', () => {
    const { track, onOpenChange } = setup();

    fire(track, pointer('pointerdown', atFraction(0.2)));
    fire(track, pointer('pointerup', atFraction(0.2)));
    onOpenChange.mockClear();
    fire(track, pointer('pointermove', atFraction(0.5)));

    expect(onOpenChange).not.toHaveBeenCalled();
  });

  it('will not let the start handle cross past the end handle', () => {
    const { track, onOpenChange } = setup({ openIndex: 40, nowIndex: 60 });

    // Aim well beyond the end handle; it must clamp to it instead.
    fire(track, pointer('pointerdown', atFraction(0.45)));
    fire(track, pointer('pointermove', atFraction(0.95)));

    expect(onOpenChange).toHaveBeenLastCalledWith(60);
  });

  it('will not let the end handle cross past the start handle', () => {
    const { track, onNowChange } = setup({ openIndex: 40, nowIndex: 60 });

    fire(track, pointer('pointerdown', atFraction(0.55)));
    fire(track, pointer('pointermove', atFraction(0.05)));

    expect(onNowChange).toHaveBeenLastCalledWith(40);
  });

  it('clamps to the track ends when dragged past them', () => {
    const { track, onOpenChange } = setup();

    fire(track, pointer('pointerdown', atFraction(0.1)));
    fire(track, pointer('pointermove', TRACK_LEFT - 500));

    expect(onOpenChange).toHaveBeenLastCalledWith(0);
  });

  it('ignores pointer input entirely when disabled', () => {
    const { track, onOpenChange, onNowChange } = setup({ disabled: true });

    fire(track, pointer('pointerdown', atFraction(0.5)));
    fire(track, pointer('pointermove', atFraction(0.6)));

    expect(onOpenChange).not.toHaveBeenCalled();
    expect(onNowChange).not.toHaveBeenCalled();
  });

  it('moves a handle with the arrow keys', () => {
    const { track, onOpenChange } = setup({ openIndex: 10, nowIndex: 90 });
    const startThumb = track.querySelectorAll('[role="slider"]')[0] as HTMLElement;

    fire(
      startThumb,
      new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true, cancelable: true })
    );

    expect(onOpenChange).toHaveBeenCalledWith(11);
  });
});
