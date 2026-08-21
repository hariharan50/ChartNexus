import { describe, expect, it } from 'vitest';
import {
  distToEllipse,
  distToLine,
  distToPolygon,
  distToPolyline,
  distToRay,
  distToRect,
  distToSegment,
  pointInPolygon
} from '../../app/lib/shared/charts/draw/geometry';
import {
  contrastText,
  extend,
  handleIndices,
  luminance,
  withAlpha,
  wrapText
} from '../../app/lib/shared/charts/draw/render';
import { allTools, drawingShortcuts, get, has } from '../../app/lib/shared/charts/draw/registry';
import { registerBuiltins } from '../../app/lib/shared/charts/draw/tools';
import { expandPosition, verdict } from '../../app/lib/shared/charts/draw/tools/positions';
import { duration, readout } from '../../app/lib/shared/charts/draw/tools/measures';
import { matchDrawingShortcut, parseChord } from '../../app/lib/shared/charts/draw/shortcuts';
import type { Bar, Drawing, RenderContext } from '../../app/lib/shared/charts/draw/types';

/**
 * The engine's arithmetic, without a canvas.
 *
 * Hit testing and the label maths are the two places a drawing tool goes wrong
 * invisibly: a shape that paints correctly but cannot be grabbed looks like a
 * broken mouse, and a position box with the wrong quantity is a number someone
 * might trade on.
 */

registerBuiltins();

describe('geometry', () => {
  const a = { x: 0, y: 0 };
  const b = { x: 10, y: 0 };

  it('measures to a segment, not to its infinite line', () => {
    expect(distToSegment(5, 3, a, b)).toBeCloseTo(3);
    // Past the end, the nearest point is the endpoint itself.
    expect(distToSegment(20, 0, a, b)).toBeCloseTo(10);
  });

  it('measures to an infinite line, which has no ends to fall off', () => {
    expect(distToLine(20, 3, a, b)).toBeCloseTo(3);
    expect(distToLine(-99, 3, a, b)).toBeCloseTo(3);
  });

  it('measures to a ray, which has one end', () => {
    expect(distToRay(20, 3, a, b)).toBeCloseTo(3);
    // Behind the origin the ray does not reach, so it falls back to the origin.
    expect(distToRay(-4, 0, a, b)).toBeCloseTo(4);
  });

  it('collapses a zero-length segment to a point rather than dividing by zero', () => {
    expect(distToSegment(3, 4, a, a)).toBeCloseTo(5);
    expect(Number.isNaN(distToSegment(3, 4, a, a))).toBe(false);
  });

  it('treats the inside of a filled rectangle as a hit and the inside of an empty one as a hole', () => {
    expect(distToRect(5, 5, 0, 0, 10, 10, true)).toBe(0);
    expect(distToRect(5, 5, 0, 0, 10, 10, false)).toBeCloseTo(5);
  });

  it('measures to the nearest rectangle edge from outside, filled or not', () => {
    expect(distToRect(15, 5, 0, 0, 10, 10, true)).toBeCloseTo(5);
    expect(distToRect(15, 5, 0, 0, 10, 10, false)).toBeCloseTo(5);
  });

  it('reads a rectangle drawn right-to-left the same as left-to-right', () => {
    expect(distToRect(5, 5, 10, 10, 0, 0, true)).toBe(0);
  });

  it('finds the nearest leg of a polyline', () => {
    const pts = [
      { x: 0, y: 0 },
      { x: 10, y: 0 },
      { x: 10, y: 10 }
    ];
    expect(distToPolyline(5, 2, pts)).toBeCloseTo(2);
    expect(distToPolyline(12, 5, pts)).toBeCloseTo(2);
  });

  it('tests a polygon by containment when filled', () => {
    const tri = [
      { x: 0, y: 0 },
      { x: 10, y: 0 },
      { x: 5, y: 10 }
    ];
    expect(pointInPolygon(5, 3, tri)).toBe(true);
    expect(pointInPolygon(5, -3, tri)).toBe(false);
    expect(distToPolygon(5, 3, tri, true)).toBe(0);
    expect(distToPolygon(5, 3, tri, false)).toBeGreaterThan(0);
  });

  it('measures to an ellipse outline and scales the error into pixels', () => {
    // Dead centre of an unfilled ellipse is one radius from the outline.
    expect(distToEllipse(0, 0, 0, 0, 10, 10, false)).toBeCloseTo(10);
    expect(distToEllipse(0, 0, 0, 0, 10, 10, true)).toBe(0);
    expect(distToEllipse(12, 0, 0, 0, 10, 10, false)).toBeCloseTo(2);
  });
});

describe('colour', () => {
  it('reads hex short, hex long and rgb', () => {
    expect(luminance('#fff')).toBeCloseTo(1);
    expect(luminance('#000000')).toBeCloseTo(0);
    expect(luminance('rgb(255, 255, 255)')).toBeCloseTo(1);
    expect(luminance('rgba(0, 0, 0, 0.5)')).toBeCloseTo(0);
  });

  it('returns a usable number rather than throwing on nonsense', () => {
    expect(luminance('not-a-colour')).toBe(0);
    expect(Number.isNaN(luminance('#12'))).toBe(false);
  });

  it('picks text that can actually be read on the plate behind it', () => {
    expect(contrastText('#ffffff')).toBe('#10131a');
    expect(contrastText('#000000')).toBe('#ffffff');
    // The mid-grey default plate leans white on a dark terminal.
    expect(contrastText('#434651')).toBe('#ffffff');
  });

  it('keeps the hue when adding alpha', () => {
    expect(withAlpha('#26a69a', 0.28)).toBe('rgba(38, 166, 154, 0.28)');
    expect(withAlpha('nonsense', 0.5)).toBe('nonsense');
  });
});

describe('extend', () => {
  const rc = { dpr: 1, plotWidth: 100, plotHeight: 100 } as RenderContext;

  it('overshoots the plot in the direction of the segment', () => {
    const [near, far] = extend({ x: 0, y: 0 }, { x: 1, y: 0 }, rc, false);
    expect(near).toEqual({ x: 0, y: 0 });
    expect(far.x).toBeGreaterThan(100);
  });

  it('overshoots both ways when the line is infinite', () => {
    const [near, far] = extend({ x: 50, y: 50 }, { x: 51, y: 50 }, rc, true);
    expect(near.x).toBeLessThan(0);
    expect(far.x).toBeGreaterThan(100);
  });

  it('gives up rather than dividing by zero on a degenerate segment', () => {
    const [near, far] = extend({ x: 5, y: 5 }, { x: 5, y: 5 }, rc, true);
    expect(near).toEqual({ x: 5, y: 5 });
    expect(far).toEqual({ x: 5, y: 5 });
  });
});

describe('handleIndices', () => {
  const drawing = (n: number): Drawing => ({
    id: 'd0',
    tool: 'brush',
    points: Array.from({ length: n }, () => ({ time: 0, price: 0 })),
    style: {},
    paneIndex: 0
  });

  it('exposes only the ends of a freehand stroke', () => {
    // Dragging a point out of the middle of a brush stroke deforms it in a way
    // nobody wants, so those handles do not exist.
    expect(handleIndices(drawing(200), true)).toEqual([0, 199]);
  });

  it('exposes every anchor of everything else', () => {
    expect(handleIndices(drawing(3), false)).toEqual([0, 1, 2]);
    // A two-point freehand is short enough that both points are its ends.
    expect(handleIndices(drawing(2), true)).toEqual([0, 1]);
  });
});

describe('registry', () => {
  it('registers all 43 built-ins', () => {
    expect(allTools()).toHaveLength(43);
  });

  it('gives every tool a unique id and a name', () => {
    const ids = allTools().map((t) => t.id);
    expect(new Set(ids).size).toBe(ids.length);
    for (const tool of allTools()) expect(tool.name.length).toBeGreaterThan(0);
  });

  it('throws a named error on an unknown tool rather than returning undefined', () => {
    expect(() => get('no-such-tool')).toThrow('unknown drawing tool "no-such-tool"');
    expect(has('no-such-tool')).toBe(false);
  });

  it('binds exactly the five documented chords', () => {
    expect(drawingShortcuts()).toEqual({
      'trend-line': 'Alt+T',
      'horizontal-line': 'Alt+H',
      'horizontal-ray': 'Alt+J',
      'vertical-line': 'Alt+V',
      'cross-line': 'Alt+C'
    });
  });

  it('registers idempotently, so a second pane costs nothing', () => {
    registerBuiltins();
    registerBuiltins();
    expect(allTools()).toHaveLength(43);
  });

  it('marks the two freehand tools and only those', () => {
    const freehand = allTools()
      .filter((t) => t.freehand === true)
      .map((t) => t.id);
    expect(freehand.sort()).toEqual(['brush', 'highlighter']);
  });

  it('gives the open-ended tools a zero point count', () => {
    const open = allTools()
      .filter((t) => t.points === 0)
      .map((t) => t.id);
    expect(open.sort()).toEqual(['brush', 'highlighter', 'path', 'polyline']);
  });
});

describe('shortcuts', () => {
  it('parses a chord into its parts', () => {
    expect(parseChord('Alt+T')).toEqual({ key: 't', alt: true, ctrl: false, shift: false });
    expect(parseChord('Ctrl+Shift+Z')).toEqual({ key: 'z', alt: false, ctrl: true, shift: true });
  });

  it('never arms a tool from a bare letter', () => {
    // Bare letters belong to the chart and to whatever the reader is typing in.
    expect(
      matchDrawingShortcut({
        key: 't',
        altKey: false,
        ctrlKey: false,
        metaKey: false,
        shiftKey: false
      })
    ).toBeNull();
  });

  it('arms on the modified chord', () => {
    expect(
      matchDrawingShortcut({
        key: 'T',
        altKey: true,
        ctrlKey: false,
        metaKey: false,
        shiftKey: false
      })
    ).toBe('trend-line');
    expect(
      matchDrawingShortcut({
        key: 'h',
        altKey: true,
        ctrlKey: false,
        metaKey: false,
        shiftKey: false
      })
    ).toBe('horizontal-line');
  });

  it('returns null for a modified key nothing claims', () => {
    expect(
      matchDrawingShortcut({
        key: 'q',
        altKey: true,
        ctrlKey: false,
        metaKey: false,
        shiftKey: false
      })
    ).toBeNull();
  });
});

describe('position expand', () => {
  const ctx = { barSeconds: 60, visibleBars: 100 };

  it('turns one click into entry, target and stop', () => {
    const [entry, target, stop] = expandPosition([{ time: 1000, price: 200 }], ctx, 1);
    expect(entry).toEqual({ time: 1000, price: 200 });
    expect(target!.price).toBeGreaterThan(200);
    expect(stop!.price).toBeLessThan(200);
    expect(target!.time).toBe(stop!.time);
  });

  it('puts the target below the entry for a short', () => {
    const [, target, stop] = expandPosition([{ time: 1000, price: 200 }], ctx, -1);
    expect(target!.price).toBeLessThan(200);
    expect(stop!.price).toBeGreaterThan(200);
  });

  it('scales the box with the instrument rather than using fixed points', () => {
    const cheap = expandPosition([{ time: 0, price: 200 }], ctx, 1);
    const index = expandPosition([{ time: 0, price: 24000 }], ctx, 1);
    expect(index[1]!.price - 24000).toBeGreaterThan(cheap[1]!.price - 200);
  });

  it('keeps a floor under the box on a near-zero price', () => {
    const [, target] = expandPosition([{ time: 0, price: 0.5 }], ctx, 1);
    expect(target!.price - 0.5).toBeGreaterThanOrEqual(1);
  });

  it('survives a click that produced no anchor', () => {
    expect(expandPosition([], ctx, 1)).toEqual([]);
  });
});

describe('forecast verdict', () => {
  const bars: Bar[] = [
    { time: 100, open: 10, high: 12, low: 9, close: 11 },
    { time: 200, open: 11, high: 15, low: 10, close: 14 }
  ];

  it('counts a wick as a hit, not just a close', () => {
    // Hit intraday and given back is still hit, and the reader can see the wick.
    expect(
      verdict(
        [
          { time: 100, price: 10 },
          { time: 200, price: 15 }
        ],
        bars
      )
    ).toBe('SUCCESS');
  });

  it('misses when nothing reached the target', () => {
    expect(
      verdict(
        [
          { time: 100, price: 10 },
          { time: 200, price: 20 }
        ],
        bars
      )
    ).toBe('MISSED');
  });

  it('reads a downward forecast against the lows', () => {
    expect(
      verdict(
        [
          { time: 100, price: 12 },
          { time: 200, price: 9 }
        ],
        bars
      )
    ).toBe('SUCCESS');
    expect(
      verdict(
        [
          { time: 100, price: 12 },
          { time: 200, price: 5 }
        ],
        bars
      )
    ).toBe('MISSED');
  });

  it('ignores bars outside the forecast window', () => {
    expect(
      verdict(
        [
          { time: 100, price: 10 },
          { time: 150, price: 15 }
        ],
        bars
      )
    ).toBe('MISSED');
  });

  it('says nothing rather than guessing when there are no bars', () => {
    expect(
      verdict(
        [
          { time: 0, price: 1 },
          { time: 1, price: 2 }
        ],
        undefined
      )
    ).toBe('FORECAST');
  });
});

describe('measure readout', () => {
  const rc = {
    priceScale: { format: (p: number) => p.toFixed(2) },
    dataLayer: { timeToIndexFloat: (t: number) => t / 60 }
  };

  it('signs the move and the percentage', () => {
    const text = readout({ time: 0, price: 100 }, { time: 300, price: 110 }, 'price', rc);
    expect(text).toContain('+10.00');
    expect(text).toContain('+10.00%');
  });

  it('signs a fall too', () => {
    const text = readout({ time: 0, price: 100 }, { time: 300, price: 90 }, 'price', rc);
    expect(text).toContain('-10.00');
    expect(text).toContain('-10.00%');
  });

  it('counts bars and duration for a date range', () => {
    const text = readout({ time: 0, price: 100 }, { time: 300, price: 110 }, 'date', rc);
    expect(text).toContain('5 bars');
  });

  it('says "bar" for one', () => {
    expect(readout({ time: 0, price: 1 }, { time: 60, price: 1 }, 'date', rc)).toContain('1 bar,');
  });

  it('does not divide by zero on a zero entry price', () => {
    const text = readout({ time: 0, price: 0 }, { time: 60, price: 5 }, 'price', rc);
    expect(text).toContain('0.00%');
  });

  it('picks the largest whole unit for a duration', () => {
    expect(duration(30)).toBe('30s');
    expect(duration(300)).toBe('5m');
    expect(duration(7200)).toBe('2.0h');
    expect(duration(172800)).toBe('2.0d');
  });
});

describe('wrapText', () => {
  // A fake metric: one unit per character, so wrapping is checkable without a canvas.
  const ctx = { measureText: (t: string) => ({ width: t.length }) } as CanvasRenderingContext2D;

  it('breaks on words, never mid-word', () => {
    expect(wrapText(ctx, 'aaa bbb ccc', 7)).toEqual(['aaa bbb', 'ccc']);
  });

  it('returns one empty line for empty input rather than nothing', () => {
    expect(wrapText(ctx, '   ', 10)).toEqual(['']);
  });

  it('keeps a single over-long word on its own line', () => {
    expect(wrapText(ctx, 'aaaaaaaaaa bb', 5)).toEqual(['aaaaaaaaaa', 'bb']);
  });
});
