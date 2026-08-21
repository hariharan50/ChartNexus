import { beforeEach, describe, expect, it } from 'vitest';
import { DrawingController } from '../../app/lib/shared/charts/draw/DrawingController';
import { makeDataLayer, barSeconds } from '../../app/lib/shared/charts/tv/drawings/data-layer';
import type {
  Bar,
  Drawing,
  HostChart,
  HostPointerEvents,
  Primitive
} from '../../app/lib/shared/charts/draw/types';

/**
 * The state machine, against a fake chart.
 *
 * The controller is the piece with no visual output to sanity-check it: a
 * missed `viaDrag` guard turns every pan into a stray trend line, and an undo
 * pushed per mouse-move silently fills a 50-deep stack with one gesture. Both
 * are invisible until a reader hits them.
 */

const BARS: Bar[] = Array.from({ length: 20 }, (_, i) => ({
  time: 1000 + i * 60,
  open: 100 + i,
  high: 105 + i,
  low: 95 + i,
  close: 102 + i
}));

class FakeChart implements HostChart {
  drawings: Drawing[] = [];
  placement = false;
  emitted: { event: string; payload: unknown }[] = [];
  primitives = new Map<number, Primitive>();

  private handlers: { [K in keyof HostPointerEvents]: ((p: HostPointerEvents[K]) => void)[] } = {
    click: [],
    'crosshair:move': [],
    drag: [],
    'drag:end': [],
    dblclick: []
  };

  dataLayer = makeDataLayer(BARS);

  on<K extends keyof HostPointerEvents>(
    event: K,
    cb: (p: HostPointerEvents[K]) => void
  ): () => void {
    (this.handlers[event] as ((p: HostPointerEvents[K]) => void)[]).push(cb);
    return () => undefined;
  }

  fire<K extends keyof HostPointerEvents>(event: K, payload: HostPointerEvents[K]): void {
    for (const cb of this.handlers[event] as ((p: HostPointerEvents[K]) => void)[]) cb(payload);
  }

  emit(event: string, payload: unknown): void {
    this.emitted.push({ event, payload });
  }

  setPlacementMode(on: boolean): void {
    this.placement = on;
  }

  drawingState(): Drawing[] {
    return this.drawings;
  }

  setDrawingState(d: Drawing[]): void {
    this.drawings = d;
  }

  getVisibleLogicalRange() {
    return { from: 0, to: 20 };
  }

  addPrimitive(paneIndex: number, primitive: Primitive): void {
    this.primitives.set(paneIndex, primitive);
  }

  removePrimitive(paneIndex: number): void {
    this.primitives.delete(paneIndex);
  }

  barAt(time: number): Bar | null {
    const i = Math.round(this.dataLayer.timeToIndexFloat(time));
    return BARS[Math.max(0, Math.min(BARS.length - 1, i))] ?? null;
  }
}

function click(
  chart: FakeChart,
  time: number,
  price: number,
  extra: Partial<{ viaDrag: boolean; externalId: string | null }> = {}
) {
  chart.fire('click', { x: 0, y: 0, time, price, paneIndex: 0, ...extra });
}

let chart: FakeChart;

beforeEach(() => {
  chart = new FakeChart();
});

describe('arming', () => {
  it('suppresses the chart’s own gestures while a tool is armed, and restores them', () => {
    const c = new DrawingController(chart);
    c.setTool('trend-line');
    expect(chart.placement).toBe(true);
    c.setTool(null);
    expect(chart.placement).toBe(false);
  });

  it('ignores an unknown tool id rather than throwing on the next click', () => {
    const c = new DrawingController(chart);
    c.setTool('no-such-tool');
    expect(c.getTool()).toBeNull();
    expect(chart.placement).toBe(false);
  });

  it('clears the selection when arming, so the style bar is not left pointed at nothing', () => {
    const c = new DrawingController(chart);
    c.setTool('horizontal-line');
    click(chart, 1060, 100);
    expect(c.selected()).not.toBeNull();
    c.setTool('trend-line');
    expect(c.selected()).toBeNull();
  });
});

describe('placement', () => {
  it('commits a two-point tool on the second click', () => {
    const c = new DrawingController(chart);
    c.setTool('trend-line');
    click(chart, 1060, 100);
    expect(c.count()).toBe(0);
    click(chart, 1300, 110);
    expect(c.count()).toBe(1);
  });

  it('commits a one-point tool immediately', () => {
    const c = new DrawingController(chart);
    c.setTool('horizontal-line');
    click(chart, 1060, 100);
    expect(c.count()).toBe(1);
  });

  it('disarms and selects the new drawing after committing', () => {
    const c = new DrawingController(chart);
    c.setTool('trend-line');
    click(chart, 1060, 100);
    click(chart, 1300, 110);
    expect(c.getTool()).toBeNull();
    expect(chart.placement).toBe(false);
    expect(c.selected()?.tool).toBe('trend-line');
  });

  it('stays armed when asked to', () => {
    const c = new DrawingController(chart, { stayInDrawingMode: true });
    c.setTool('horizontal-line');
    click(chart, 1060, 100);
    click(chart, 1120, 105);
    expect(c.count()).toBe(2);
    expect(c.getTool()).toBe('horizontal-line');
  });

  it('treats a drag with nothing pending as a pan, not a placement', () => {
    const c = new DrawingController(chart);
    c.setTool('trend-line');
    click(chart, 1060, 100, { viaDrag: true });
    expect(c.count()).toBe(0);
    // ...and nothing was left half-placed either.
    click(chart, 1300, 110);
    expect(c.count()).toBe(0);
  });

  it('refuses a click that landed off the data', () => {
    const c = new DrawingController(chart);
    c.setTool('horizontal-line');
    chart.fire('click', { x: 0, y: 0, time: null, price: null, paneIndex: 0 });
    expect(c.count()).toBe(0);
  });

  it('merges style with the tool default beating the workspace default', () => {
    const c = new DrawingController(chart, { defaultStyle: { color: '#123456', fill: false } });
    c.setTool('rectangle');
    click(chart, 1060, 100);
    click(chart, 1300, 110);
    const drawing = c.selected()!;
    expect(drawing.style.color).toBe('#123456');
    // `rectangle` ships `fill: true`, which is more specific than the house style.
    expect(drawing.style.fill).toBe(true);
  });
});

describe('open-ended tools', () => {
  it('collects anchors until finish()', () => {
    const c = new DrawingController(chart);
    c.setTool('path');
    click(chart, 1060, 100);
    click(chart, 1120, 105);
    click(chart, 1180, 102);
    expect(c.count()).toBe(0);
    chart.fire('dblclick', { x: 0, y: 0, time: 1180, price: 102, paneIndex: 0 });
    expect(c.count()).toBe(1);
    expect(c.selected()?.points).toHaveLength(3);
  });

  it('throws away a one-click path rather than leaving an invisible dot', () => {
    const c = new DrawingController(chart);
    c.setTool('path');
    click(chart, 1060, 100);
    chart.fire('dblclick', { x: 0, y: 0, time: 1060, price: 100, paneIndex: 0 });
    expect(c.count()).toBe(0);
  });
});

describe('magnet', () => {
  it('snaps to the nearest O/H/L/C of the hovered bar', () => {
    const c = new DrawingController(chart, { magnet: true });
    c.setTool('horizontal-line');
    chart.fire('crosshair:move', { x: 0, y: 0, time: 1000, price: 104, paneIndex: 0 });
    click(chart, 1000, 104);
    // Bar 0 is o100 h105 l95 c102; 104 is nearest the high.
    expect(c.selected()?.points[0]?.price).toBe(105);
  });

  it('leaves the price alone with the magnet off', () => {
    const c = new DrawingController(chart);
    c.setTool('horizontal-line');
    chart.fire('crosshair:move', { x: 0, y: 0, time: 1000, price: 104, paneIndex: 0 });
    click(chart, 1000, 104);
    expect(c.selected()?.points[0]?.price).toBe(104);
  });

  it('never snaps in a sub-pane, where an indicator’s values are not candle prices', () => {
    const c = new DrawingController(chart, { magnet: true });
    c.setTool('horizontal-line');
    chart.fire('crosshair:move', { x: 0, y: 0, time: 1000, price: 104, paneIndex: 0 });
    chart.fire('click', { x: 0, y: 0, time: 1000, price: 104, paneIndex: 1 });
    expect(c.selected()?.points[0]?.price).toBe(104);
  });
});

describe('selection and dragging', () => {
  function placed(): DrawingController {
    const c = new DrawingController(chart);
    c.setTool('trend-line');
    click(chart, 1060, 100);
    click(chart, 1300, 110);
    return c;
  }

  it('selects by clicking a drawing and deselects by clicking empty chart', () => {
    const c = placed();
    const id = c.selected()!.id;
    c.select(null);
    click(chart, 1200, 105, { externalId: `draw:${id}` });
    expect(c.selected()?.id).toBe(id);
    click(chart, 1200, 105, { externalId: null });
    expect(c.selected()).toBeNull();
  });

  it('moves every anchor by the same delta when the body is dragged', () => {
    const c = placed();
    const id = c.selected()!.id;
    const before = c.selected()!.points.map((p) => ({ ...p }));
    chart.fire('drag', {
      x: 0,
      y: 0,
      time: 1120,
      price: 105,
      paneIndex: 0,
      fromTime: 1060,
      fromPrice: 100,
      externalId: `draw:${id}`
    });
    const after = c.selected()!.points;
    expect(after[0]!.time - before[0]!.time).toBe(60);
    expect(after[1]!.time - before[1]!.time).toBe(60);
    expect(after[0]!.price - before[0]!.price).toBeCloseTo(5);
    expect(after[1]!.price - before[1]!.price).toBeCloseTo(5);
  });

  it('moves only the grabbed anchor when a handle is dragged', () => {
    const c = placed();
    const id = c.selected()!.id;
    const before = c.selected()!.points.map((p) => ({ ...p }));
    chart.fire('drag', {
      x: 0,
      y: 0,
      time: 1500,
      price: 130,
      paneIndex: 0,
      fromTime: 1300,
      fromPrice: 110,
      externalId: `draw:${id}#1`
    });
    const after = c.selected()!.points;
    expect(after[0]).toEqual(before[0]);
    expect(after[1]).toEqual({ time: 1500, price: 130 });
  });

  it('refuses to move a locked drawing at all', () => {
    const c = placed();
    const id = c.selected()!.id;
    c.update(id, { locked: true });
    const before = JSON.stringify(c.selected()!.points);
    chart.fire('drag', {
      x: 0,
      y: 0,
      time: 1120,
      price: 105,
      paneIndex: 0,
      fromTime: 1060,
      fromPrice: 100,
      externalId: `draw:${id}`
    });
    expect(JSON.stringify(c.selected()!.points)).toBe(before);
  });

  it('records one undo step per gesture, not one per mouse-move', () => {
    const c = placed();
    const id = c.selected()!.id;
    // Placing pushed one entry; the drag below must add exactly one more.
    for (let i = 0; i < 20; i += 1) {
      chart.fire('drag', {
        x: 0,
        y: 0,
        time: 1060 + i,
        price: 100 + i,
        paneIndex: 0,
        fromTime: 1060,
        fromPrice: 100,
        externalId: `draw:${id}`
      });
    }
    chart.fire('drag:end', {
      x: 0,
      y: 0,
      time: 1080,
      price: 120,
      paneIndex: 0,
      fromTime: 1060,
      fromPrice: 100,
      externalId: `draw:${id}`
    });
    c.undo();
    // One undo returns the drawing to where it was placed, not to mid-drag.
    expect(c.count()).toBe(1);
    expect(c.selected()?.points[0]?.time ?? 0).toBe(1060);
  });
});

describe('freehand', () => {
  it('inks on drag and commits on drag end', () => {
    const c = new DrawingController(chart);
    c.setTool('brush');
    for (let i = 0; i < 5; i += 1) {
      chart.fire('drag', {
        x: 0,
        y: 0,
        time: 1000 + i * 60,
        price: 100 + i,
        paneIndex: 0,
        fromTime: 1000,
        fromPrice: 100
      });
    }
    chart.fire('drag:end', {
      x: 0,
      y: 0,
      time: 1240,
      price: 104,
      paneIndex: 0,
      fromTime: 1000,
      fromPrice: 100
    });
    expect(c.count()).toBe(1);
    expect(c.selected()?.points).toHaveLength(5);
  });

  it('swallows the click that merely terminated the stroke', () => {
    const c = new DrawingController(chart);
    c.setTool('brush');
    chart.fire('drag', {
      x: 0,
      y: 0,
      time: 1000,
      price: 100,
      paneIndex: 0,
      fromTime: 1000,
      fromPrice: 100
    });
    chart.fire('drag', {
      x: 0,
      y: 0,
      time: 1060,
      price: 101,
      paneIndex: 0,
      fromTime: 1000,
      fromPrice: 100
    });
    chart.fire('drag:end', {
      x: 0,
      y: 0,
      time: 1060,
      price: 101,
      paneIndex: 0,
      fromTime: 1000,
      fromPrice: 100
    });
    click(chart, 1060, 101, { viaDrag: true });
    expect(c.count()).toBe(1);
  });
});

describe('history', () => {
  it('undoes and redoes a placement', () => {
    const c = new DrawingController(chart);
    c.setTool('horizontal-line');
    click(chart, 1060, 100);
    expect(c.count()).toBe(1);
    c.undo();
    expect(c.count()).toBe(0);
    c.redo();
    expect(c.count()).toBe(1);
  });

  it('reports what it can do', () => {
    const c = new DrawingController(chart);
    expect(c.canUndo()).toBe(false);
    expect(c.canRedo()).toBe(false);
    c.setTool('horizontal-line');
    click(chart, 1060, 100);
    expect(c.canUndo()).toBe(true);
    c.undo();
    expect(c.canRedo()).toBe(true);
  });

  it('orphans the redo branch on a new edit — there is no tree here', () => {
    const c = new DrawingController(chart, { stayInDrawingMode: true });
    c.setTool('horizontal-line');
    click(chart, 1060, 100);
    c.undo();
    expect(c.canRedo()).toBe(true);
    click(chart, 1120, 105);
    expect(c.canRedo()).toBe(false);
  });

  it('caps the stack, so a long session cannot grow without bound', () => {
    const c = new DrawingController(chart, { stayInDrawingMode: true, historyLimit: 3 });
    c.setTool('horizontal-line');
    for (let i = 0; i < 10; i += 1) click(chart, 1000 + i * 60, 100 + i);
    let undos = 0;
    while (c.canUndo() && undos < 20) {
      c.undo();
      undos += 1;
    }
    expect(undos).toBe(3);
  });
});

describe('persistence', () => {
  it('round-trips losslessly', () => {
    const c = new DrawingController(chart);
    c.setTool('trend-line');
    click(chart, 1060, 100);
    click(chart, 1300, 110);
    const json = c.toJSON();

    const other = new DrawingController(new FakeChart());
    other.fromJSON(json);
    expect(other.toJSON()).toEqual(json);
  });

  it('hands back a clone, so a caller stashing it cannot mutate live state', () => {
    const c = new DrawingController(chart);
    c.setTool('horizontal-line');
    click(chart, 1060, 100);
    const json = c.toJSON();
    json[0]!.points[0]!.price = 999;
    expect(c.toJSON()[0]!.points[0]!.price).toBe(100);
  });

  it('preserves style keys it has never heard of', () => {
    const saved: Drawing[] = [
      {
        id: 'd0',
        tool: 'trend-line',
        paneIndex: 0,
        points: [
          { time: 1000, price: 1 },
          { time: 1060, price: 2 }
        ],
        style: { color: '#fff', somethingNewer: 42 }
      }
    ];
    const c = new DrawingController(chart);
    c.fromJSON(saved);
    expect(c.toJSON()[0]!.style.somethingNewer).toBe(42);
  });

  it('moves the id counter past restored drawings, so the next placement cannot collide', () => {
    const saved: Drawing[] = [
      {
        id: 'd7',
        tool: 'horizontal-line',
        paneIndex: 0,
        points: [{ time: 1000, price: 1 }],
        style: {}
      }
    ];
    const c = new DrawingController(chart);
    c.fromJSON(saved);
    c.setTool('horizontal-line');
    click(chart, 1060, 100);
    const ids = c.toJSON().map((d) => d.id);
    expect(new Set(ids).size).toBe(ids.length);
    expect(ids).toContain('d8');
  });

  it('drops malformed entries rather than rejecting the whole workspace', () => {
    const c = new DrawingController(chart);
    c.fromJSON([
      {
        id: 'd0',
        tool: 'trend-line',
        paneIndex: 0,
        points: [
          { time: 1, price: 1 },
          { time: 2, price: 2 }
        ],
        style: {}
      },
      { id: 'd1', tool: 'trend-line', paneIndex: 0, style: {} } as unknown as Drawing
    ]);
    expect(c.count()).toBe(1);
  });
});

describe('teardown', () => {
  it('is snapshottable right up until destroy()', () => {
    const c = new DrawingController(chart);
    c.setTool('horizontal-line');
    click(chart, 1060, 100);
    const json = c.toJSON();
    c.destroy();
    expect(json).toHaveLength(1);
    expect(chart.primitives.size).toBe(0);
    expect(chart.placement).toBe(false);
  });
});

describe('data layer', () => {
  const layer = makeDataLayer(BARS);

  it('round-trips a bar’s own time', () => {
    expect(layer.timeToIndexFloat(BARS[5]!.time)).toBeCloseTo(5);
    expect(layer.indexToTime(5)).toBe(BARS[5]!.time);
  });

  it('interpolates between bars', () => {
    expect(layer.timeToIndexFloat(BARS[5]!.time + 30)).toBeCloseTo(5.5);
  });

  it('keeps counting past the last bar, which is where every forecast lives', () => {
    // The library's own conversion returns null out here; a position target
    // three days ahead has to land somewhere.
    expect(layer.timeToIndexFloat(BARS[19]!.time + 600)).toBeCloseTo(29);
    expect(layer.indexToTime(29)).toBe(BARS[19]!.time + 600);
  });

  it('extends backwards before the first bar too', () => {
    expect(layer.timeToIndexFloat(BARS[0]!.time - 120)).toBeCloseTo(-2);
  });

  it('survives an empty series', () => {
    const empty = makeDataLayer([]);
    expect(empty.indexToTime(3)).toBe(0);
    expect(empty.timeToIndexFloat(999)).toBe(0);
  });

  it('takes the median gap, so one weekend does not stretch every projection', () => {
    const gappy = [
      ...BARS.slice(0, 10),
      { time: BARS[9]!.time + 200000, open: 1, high: 1, low: 1, close: 1 }
    ];
    expect(barSeconds(gappy)).toBeLessThan(1000);
  });
});
