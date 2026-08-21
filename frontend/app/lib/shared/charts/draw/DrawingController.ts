/**
 * The drawing state machine.
 *
 * Everything the reader does to a drawing passes through here: arming a tool,
 * placing anchors, the live preview, committing, selecting, dragging a body or
 * a handle, undo/redo, and the JSON round trip. The host chart supplies the
 * pointer stream and a canvas to paint on; this decides what any of it means.
 *
 * It is deliberately not a React thing. The hook in `../tv/drawings/useDrawings`
 * owns one of these and mirrors its stats into state — but the controller
 * itself would run just as well against a chart in a worker, which is what
 * keeps it testable without a DOM.
 */

import { Layer, PREVIEW_ID } from './Layer';
import { get, has } from './registry';
import { registerBuiltins } from './tools';
import type {
  Bar,
  ChartDragEvent,
  ChartPointerEvent,
  Drawing,
  DrawingStyle,
  HostChart,
  Point
} from './types';

export interface ControllerOptions {
  magnet?: boolean;
  /** Keep the tool armed after a commit, for placing several in a row. */
  stayInDrawingMode?: boolean;
  historyLimit?: number;
  defaultStyle?: DrawingStyle;
}

export interface AddInput {
  tool: string;
  points: Point[];
  paneIndex?: number;
  style?: DrawingStyle;
}

const DEFAULT_HISTORY = 50;

export class DrawingController {
  private readonly chart: HostChart;
  private options: Required<
    Pick<ControllerOptions, 'magnet' | 'stayInDrawingMode' | 'historyLimit'>
  > & {
    defaultStyle: DrawingStyle;
  };

  private drawings: Drawing[] = [];
  private selectedId: string | null = null;
  private tool: string | null = null;
  /** Anchors placed so far for the shape being drawn. */
  private pending: Point[] = [];
  private pendingPane = 0;
  /** Last crosshair position, which is what the preview's far end follows. */
  private cursor: Point | null = null;
  private readonly layers = new Map<number, Layer>();
  private undoStack: string[] = [];
  private redoStack: string[] = [];
  private lastBar: Bar | null = null;
  private counter = 0;
  private readonly unsubscribes: (() => void)[] = [];
  private destroyed = false;
  /** Guards `_pushUndo` to once per drag gesture rather than once per move. */
  private draggingId: string | null = null;

  constructor(chart: HostChart, options: ControllerOptions = {}) {
    registerBuiltins();
    this.chart = chart;
    this.options = {
      magnet: options.magnet ?? false,
      stayInDrawingMode: options.stayInDrawingMode ?? false,
      historyLimit: options.historyLimit ?? DEFAULT_HISTORY,
      defaultStyle: options.defaultStyle ?? {}
    };

    const seed = chart.drawingState();
    if (seed.length > 0) this.hydrate(seed);

    this.unsubscribes.push(
      chart.on('click', (e) => this.onClick(e)),
      chart.on('crosshair:move', (e) => this.onMove(e)),
      chart.on('drag', (e) => this.onDrag(e)),
      chart.on('drag:end', (e) => this.onDragEnd(e)),
      chart.on('dblclick', () => this.finish())
    );
    this.sync();
  }

  // -- tool ------------------------------------------------------------------

  getTool(): string | null {
    return this.tool;
  }

  setTool(id: string | null): void {
    if (id !== null && !has(id)) return;
    this.pending = [];
    this.clearPreview();
    this.tool = id;
    this.chart.setPlacementMode(id !== null);
    // Arming clears the selection: the style bar belongs to a finished drawing,
    // and leaving it up while placing a new one is a control pointed at the
    // wrong object.
    if (id !== null) this.select(null);
    this.chart.emit('draw:tool', { tool: id });
  }

  setOptions(patch: ControllerOptions): void {
    this.options = {
      ...this.options,
      ...patch,
      defaultStyle: patch.defaultStyle ?? this.options.defaultStyle
    };
  }

  // -- collection ------------------------------------------------------------

  add(input: AddInput): Drawing {
    const def = get(input.tool);
    const drawing: Drawing = {
      id: `d${this.counter++}`,
      tool: input.tool,
      points: input.points,
      paneIndex: input.paneIndex ?? 0,
      // Later wins: a caller's explicit style beats the tool's default, which
      // beats whatever the workspace has set as its house style.
      style: { ...this.options.defaultStyle, ...def.defaultStyle, ...input.style }
    };
    this.pushUndo();
    this.drawings = [...this.drawings, drawing];
    this.sync();
    this.chart.emit('draw:add', { drawing });
    return drawing;
  }

  update(
    id: string,
    patch: { style?: DrawingStyle; points?: Point[]; locked?: boolean; visible?: boolean }
  ): void {
    const index = this.drawings.findIndex((d) => d.id === id);
    if (index === -1) return;
    const current = this.drawings[index]!;
    const next: Drawing = {
      ...current,
      ...(patch.points ? { points: patch.points } : {}),
      ...(patch.locked !== undefined ? { locked: patch.locked } : {}),
      ...(patch.visible !== undefined ? { visible: patch.visible } : {}),
      style: patch.style ? { ...current.style, ...patch.style } : current.style
    };
    this.drawings = this.drawings.map((d, i) => (i === index ? next : d));
    this.sync();
    this.chart.emit('draw:update', { drawing: next });
  }

  remove(id: string): void {
    if (!this.drawings.some((d) => d.id === id)) return;
    this.pushUndo();
    this.drawings = this.drawings.filter((d) => d.id !== id);
    if (this.selectedId === id) this.select(null);
    this.sync();
    this.chart.emit('draw:remove', { id });
  }

  removeAll(): void {
    if (this.drawings.length === 0) return;
    this.pushUndo();
    this.drawings = [];
    this.select(null);
    this.sync();
    this.chart.emit('draw:update', {
      drawing: { id: '', tool: '', points: [], style: {}, paneIndex: 0 }
    });
  }

  count(): number {
    return this.drawings.length;
  }

  select(id: string | null): void {
    const next = id !== null && this.drawings.some((d) => d.id === id) ? id : null;
    if (next === this.selectedId) return;
    this.selectedId = next;
    for (const layer of this.layers.values()) layer.setSelected(next);
    this.chart.emit('draw:select', { id: next });
  }

  selected(): Drawing | null {
    return this.drawings.find((d) => d.id === this.selectedId) ?? null;
  }

  // -- placement -------------------------------------------------------------

  private onClick(e: ChartPointerEvent): void {
    if (this.destroyed) return;

    if (!this.tool) {
      // Selection mode.
      const id = e.externalId;
      if (id?.startsWith('draw:')) this.select(idOf(id));
      else if (id == null) this.select(null);
      return;
    }

    const def = get(this.tool);
    // Freehand shapes are committed by `drag:end`; the click that merely ended
    // that gesture must not also place an anchor.
    if (def.freehand === true && e.viaDrag === true) return;
    // A drag that placed nothing was a pan, not a placement.
    if (e.viaDrag === true && this.pending.length === 0) return;
    if (e.time === null || e.price === null) return;
    if (!Number.isFinite(e.time) || !Number.isFinite(e.price)) return;

    this.pendingPane = e.paneIndex;
    this.pending.push({ time: e.time, price: this.snap(e.price, e.paneIndex) });

    if (def.points !== 0 && this.pending.length >= def.points) this.commit(e.paneIndex);
    else this.syncPreview(e.paneIndex);
  }

  private onMove(e: ChartPointerEvent): void {
    if (this.destroyed) return;
    if (e.time !== null) this.lastBar = this.chart.barAt(e.time);
    if (e.time === null || e.price === null) return;
    this.cursor = { time: e.time, price: this.snap(e.price, e.paneIndex) };
    if (this.pending.length > 0) this.syncPreview(this.pendingPane);
  }

  /**
   * Snaps to the nearest O/H/L/C of the hovered bar.
   *
   * Main pane only. A sub-pane holds an indicator, whose values have nothing to
   * do with the price bars, so snapping an anchor there to a candle's high
   * would put it somewhere meaningless.
   */
  private snap(price: number, paneIndex: number): number {
    if (!this.options.magnet || paneIndex !== 0 || !this.lastBar) return price;
    const bar = this.lastBar;
    let best = price;
    let bestGap = Infinity;
    for (const candidate of [bar.open, bar.high, bar.low, bar.close]) {
      const gap = Math.abs(candidate - price);
      if (gap < bestGap) {
        bestGap = gap;
        best = candidate;
      }
    }
    return best;
  }

  private commit(paneIndex: number): void {
    const tool = this.tool;
    if (!tool) return;
    const def = get(tool);
    let points = this.pending;
    if (def.expand) points = def.expand(points, this.expandContext());

    this.pending = [];
    this.clearPreview();
    const drawing = this.add({ tool, points, paneIndex, style: {} });

    if (!this.options.stayInDrawingMode) {
      this.tool = null;
      this.chart.setPlacementMode(false);
    }
    this.select(drawing.id);
    this.chart.emit('draw:tool', { tool: this.tool });
  }

  /** Ends an open-ended tool (`points: 0`). Fired by a double-click, or called directly. */
  finish(): void {
    if (!this.tool || this.pending.length === 0) return;
    const def = get(this.tool);
    if (def.points !== 0) return;
    // A path needs two anchors to be a path; one click plus a double-click is a
    // stray dot the reader cannot see and cannot select.
    if (this.pending.length < 2) {
      this.pending = [];
      this.clearPreview();
      return;
    }
    this.commit(this.pendingPane);
  }

  private expandContext(): { barSeconds: number; visibleBars: number } {
    const { dataLayer } = this.chart;
    const base = dataLayer.baseIndex;
    const barSeconds =
      Math.abs(dataLayer.indexToTime(base) - dataLayer.indexToTime(base - 1)) || 60;
    const range = this.chart.getVisibleLogicalRange();
    const visibleBars = range ? Math.abs(range.to - range.from) : 100;
    return { barSeconds, visibleBars };
  }

  // -- preview ---------------------------------------------------------------

  private syncPreview(paneIndex: number): void {
    if (this.pending.length === 0 || !this.tool) return;
    const points = this.cursor ? [...this.pending, this.cursor] : [...this.pending];
    this.layerFor(paneIndex).setPreview({
      id: PREVIEW_ID,
      tool: this.tool,
      points,
      style: this.options.defaultStyle,
      paneIndex
    });
  }

  private clearPreview(): void {
    for (const layer of this.layers.values()) layer.setPreview(null);
  }

  // -- freehand & dragging ---------------------------------------------------

  private onDrag(e: ChartDragEvent): void {
    if (this.destroyed || e.time === null || e.price === null) return;

    if (this.tool) {
      const def = get(this.tool);
      if (def.freehand === true) {
        this.pendingPane = e.paneIndex;
        this.pending.push({ time: e.time, price: e.price });
        this.syncPreview(e.paneIndex);
      }
      return;
    }

    const externalId = e.externalId;
    if (!externalId?.startsWith('draw:')) return;
    const id = idOf(externalId);
    const drawing = this.drawings.find((d) => d.id === id);
    if (!drawing || drawing.locked === true) return;

    // One undo entry per gesture. Pushing per move would fill the 50-deep stack
    // with a single drag and make undo useless.
    if (this.draggingId !== id) {
      this.pushUndo();
      this.draggingId = id;
      this.select(id);
    }

    const handle = handleOf(externalId);
    const points =
      handle === null
        ? drawing.points.map((p) => ({
            time: p.time + (e.time! - e.fromTime),
            price: p.price + (e.price! - e.fromPrice)
          }))
        : drawing.points.map((p, i) =>
            i === handle ? { time: e.time!, price: this.snap(e.price!, e.paneIndex) } : p
          );

    this.drawings = this.drawings.map((d) => (d.id === id ? { ...d, points } : d));
    this.syncLayers();
  }

  private onDragEnd(e: ChartDragEvent): void {
    if (this.destroyed) return;

    if (this.tool) {
      const def = get(this.tool);
      if (def.freehand === true && this.pending.length > 1) {
        this.commit(e.paneIndex);
        return;
      }
      if (def.freehand === true) {
        this.pending = [];
        this.clearPreview();
      }
      return;
    }

    const id = this.draggingId;
    this.draggingId = null;
    if (!id) return;
    const drawing = this.drawings.find((d) => d.id === id);
    this.sync();
    if (drawing) this.chart.emit('draw:update', { drawing });
  }

  // -- history ---------------------------------------------------------------

  private pushUndo(): void {
    this.undoStack.push(JSON.stringify(this.drawings));
    if (this.undoStack.length > this.options.historyLimit) this.undoStack.shift();
    // Any new edit orphans the redo branch — there is no tree here, just a line.
    this.redoStack = [];
  }

  canUndo(): boolean {
    return this.undoStack.length > 0;
  }

  canRedo(): boolean {
    return this.redoStack.length > 0;
  }

  undo(): void {
    const previous = this.undoStack.pop();
    if (previous === undefined) return;
    this.redoStack.push(JSON.stringify(this.drawings));
    this.restore(previous);
  }

  redo(): void {
    const next = this.redoStack.pop();
    if (next === undefined) return;
    this.undoStack.push(JSON.stringify(this.drawings));
    this.restore(next);
  }

  private restore(json: string): void {
    try {
      this.drawings = JSON.parse(json) as Drawing[];
    } catch {
      return;
    }
    if (!this.drawings.some((d) => d.id === this.selectedId)) this.select(null);
    this.sync();
    const selected = this.selected();
    if (selected) this.chart.emit('draw:update', { drawing: selected });
    else this.chart.emit('draw:select', { id: null });
  }

  // -- persistence -----------------------------------------------------------

  toJSON(): Drawing[] {
    // A structured clone, so a caller stashing this cannot mutate live state.
    return JSON.parse(JSON.stringify(this.drawings)) as Drawing[];
  }

  fromJSON(drawings: Drawing[]): void {
    this.hydrate(drawings);
    this.select(null);
    this.sync();
  }

  /**
   * Adopts a set of drawings and moves the id counter past them.
   *
   * Without that last part a restored workspace would mint `d0` again on the
   * next placement and collide with the `d0` it just loaded — two drawings with
   * one id, where selecting either selects the wrong one.
   */
  private hydrate(drawings: Drawing[]): void {
    this.drawings = drawings.filter((d) => Array.isArray(d.points) && typeof d.tool === 'string');
    let max = -1;
    for (const drawing of this.drawings) {
      const n = Number.parseInt(drawing.id.replace(/^d/, ''), 10);
      if (Number.isFinite(n)) max = Math.max(max, n);
    }
    this.counter = max + 1;
  }

  // -- layers ----------------------------------------------------------------

  private layerFor(paneIndex: number): Layer {
    let layer = this.layers.get(paneIndex);
    if (!layer) {
      layer = new Layer();
      layer.setSelected(this.selectedId);
      this.layers.set(paneIndex, layer);
      this.chart.addPrimitive(paneIndex, layer);
    }
    return layer;
  }

  private syncLayers(): void {
    const byPane = new Map<number, Drawing[]>();
    for (const drawing of this.drawings) {
      const bucket = byPane.get(drawing.paneIndex);
      if (bucket) bucket.push(drawing);
      else byPane.set(drawing.paneIndex, [drawing]);
    }
    for (const [paneIndex, bucket] of byPane) this.layerFor(paneIndex).setDrawings(bucket);
    // Panes that lost their last drawing keep their (now empty) layer: the cost
    // is one no-op draw call per frame, against tearing a primitive off the
    // chart and putting it straight back the next time the reader draws there.
    for (const [paneIndex, layer] of this.layers) {
      if (!byPane.has(paneIndex)) layer.setDrawings([]);
    }
  }

  private sync(): void {
    this.syncLayers();
    this.chart.setDrawingState(this.toJSON());
  }

  destroy(): void {
    this.destroyed = true;
    for (const unsubscribe of this.unsubscribes) unsubscribe();
    this.unsubscribes.length = 0;
    for (const [paneIndex, layer] of this.layers) this.chart.removePrimitive(paneIndex, layer);
    this.layers.clear();
    this.chart.setPlacementMode(false);
    this.drawings = [];
    this.undoStack = [];
    this.redoStack = [];
  }
}

/** `draw:d3#1` -> `d3` */
function idOf(externalId: string): string {
  return externalId.slice(5).split('#')[0] ?? '';
}

/** `draw:d3#1` -> `1`; a bare body id -> `null`. */
function handleOf(externalId: string): number | null {
  const part = externalId.split('#')[1];
  if (part === undefined) return null;
  const n = Number.parseInt(part, 10);
  return Number.isFinite(n) ? n : null;
}
