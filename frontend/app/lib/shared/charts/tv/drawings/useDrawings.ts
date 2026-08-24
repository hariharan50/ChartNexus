/**
 * The React face of the drawing engine.
 *
 * One of these per chart cell. It owns a `LightweightHost` and a
 * `DrawingController`, mirrors the controller's state into the small
 * projections the UI actually renders (`DrawStats`, `DrawSelection`,
 * `DrawTextStyle`), and persists to localStorage under a per-cell key.
 *
 * The engine arrives through a dynamic `import()` on the first drawing
 * interaction — arming a tool, or finding saved drawings to restore. A chart
 * nobody draws on never loads 43 tools' worth of geometry.
 */

import { useCallback, useEffect, useRef, useState, type RefObject } from 'react';
import type * as DrawEngine from '../../draw';
import type { Drawing, DrawingStyle } from '../../draw/types';
import type { ChartTheme } from '../../theme/types';
import type { Candle, LwChartHandle } from '../LwChart';
import { LightweightHost } from './lw-host';

/** Text-bearing tools open the editor on placement. */
const TEXT_TOOLS = new Set(['text', 'callout', 'price-label']);

export interface DrawStats {
  count: number;
  canUndo: boolean;
  canRedo: boolean;
  hasSelection: boolean;
  magnet: boolean;
  tool: string | null;
  shortcuts: Record<string, string>;
}

export interface DrawSelection {
  id: string;
  tool: string;
  hasText: boolean;
  color: string;
  lineWidth: number;
  lineStyle: string;
  locked: boolean;
}

export interface DrawTextStyle {
  text: string;
  color: string;
  fontSize: number;
  bold: boolean;
  italic: boolean;
  background: boolean;
  backgroundColor: string;
  border: boolean;
  borderColor: string;
  wrap: boolean;
}

export interface TextRequest {
  id: string;
  tool: string;
  style: DrawTextStyle;
}

export const EMPTY_STATS: DrawStats = {
  count: 0,
  canUndo: false,
  canRedo: false,
  hasSelection: false,
  magnet: false,
  tool: null,
  shortcuts: {}
};

interface Options {
  handleRef: RefObject<LwChartHandle | null>;
  containerRef: RefObject<HTMLDivElement | null>;
  candles: Candle[];
  theme: ChartTheme;
  /** Bumped by `LwChart` when it rebuilds its chart and series. */
  chartEpoch: number;
  /** Distinguishes this cell's saved drawings from its neighbours'. */
  storageKey: string;
  tool: string | null;
  magnet: boolean;
  /** Freezes every drawing on this chart. */
  locked: boolean;
  visible: boolean;
  onToolDone: () => void;
}

export interface DrawingsApi {
  stats: DrawStats;
  selection: DrawSelection | null;
  textRequest: TextRequest | null;
  undo: () => void;
  redo: () => void;
  remove: (all: boolean) => void;
  style: (patch: {
    color?: string;
    lineWidth?: number;
    lineStyle?: string;
    locked?: boolean;
  }) => void;
  editSelectedText: () => void;
  applyText: (id: string, value: DrawTextStyle) => void;
  closeText: () => void;
  /** Returns true when the keystroke armed a tool. */
  armByShortcut: (event: KeyboardEvent) => string | null;
}

// Type-only, so this names the engine's shape without emitting an import of it —
// the actual module still arrives through the `await import()` below.
type Engine = typeof DrawEngine;
type Controller = InstanceType<Engine['DrawingController']>;

export function useDrawings(options: Options): DrawingsApi {
  const {
    handleRef,
    containerRef,
    candles,
    theme,
    chartEpoch,
    storageKey,
    tool,
    magnet,
    locked,
    visible,
    onToolDone
  } = options;

  const [stats, setStats] = useState<DrawStats>(EMPTY_STATS);
  const [selection, setSelection] = useState<DrawSelection | null>(null);
  const [textRequest, setTextRequest] = useState<TextRequest | null>(null);

  const engineRef = useRef<Engine | null>(null);
  const hostRef = useRef<LightweightHost | null>(null);
  const controllerRef = useRef<Controller | null>(null);
  const aliveRef = useRef(true);
  /** Everything the async attach needs but must not re-run for. */
  const latest = useRef({ candles, theme, magnet, locked, visible, onToolDone, storageKey });
  latest.current = { candles, theme, magnet, locked, visible, onToolDone, storageKey };

  useEffect(() => {
    aliveRef.current = true;
    return () => {
      aliveRef.current = false;
    };
  }, []);

  const publish = useCallback(() => {
    const controller = controllerRef.current;
    const engine = engineRef.current;
    if (!controller || !engine || !aliveRef.current) return;
    const selected = controller.selected();
    setStats({
      count: controller.count(),
      canUndo: controller.canUndo(),
      canRedo: controller.canRedo(),
      hasSelection: selected !== null,
      magnet: latest.current.magnet,
      tool: controller.getTool(),
      shortcuts: engine.drawingShortcuts()
    });
    setSelection(selected ? projectSelection(selected) : null);
    save(latest.current.storageKey, controller.toJSON());
  }, []);

  // -- attach ---------------------------------------------------------------
  // Keyed on the chart epoch: `LwChart` throws its chart and series away on a
  // type switch, so the host has to be rebuilt against the new pair. The
  // drawings themselves survive, because they are `{time, price}` and get
  // re-seeded from storage below.
  useEffect(() => {
    let cancelled = false;
    const api = handleRef.current?.getApi();
    const container = containerRef.current;
    if (!api || !container) return;

    // Nothing to draw and nothing saved: stay lazy.
    const saved = load(storageKey);
    if (saved.length === 0 && tool === null && controllerRef.current === null) return;

    void (async () => {
      const engine = engineRef.current ?? (await import('../../draw'));
      // The await is a suspension point — the cell may have unmounted, or the
      // chart been rebuilt again, while the engine was in flight.
      if (cancelled || !aliveRef.current) return;
      engineRef.current = engine;

      const current = handleRef.current?.getApi();
      if (!current) return;

      controllerRef.current?.destroy();
      hostRef.current?.destroy();

      const host = new LightweightHost({
        chart: current.chart,
        series: current.series,
        container,
        candles: latest.current.candles,
        theme: latest.current.theme,
        initial: saved,
        onState: (drawings) => save(latest.current.storageKey, drawings)
      });
      hostRef.current = host;

      const controller = new engine.DrawingController(host, {
        magnet: latest.current.magnet,
        stayInDrawingMode: false,
        defaultStyle: { color: latest.current.theme.accent }
      });
      controllerRef.current = controller;

      host.onEmit('draw:add', (payload) => {
        const drawing = (payload as { drawing: Drawing }).drawing;
        // A note with no words is not a note. Open the editor straight away so
        // the reader never has to discover that the empty box is editable.
        if (drawing && TEXT_TOOLS.has(drawing.tool)) {
          const style = textStyleOf(drawing);
          if (aliveRef.current) setTextRequest({ id: drawing.id, tool: drawing.tool, style });
        }
        publish();
      });
      for (const event of ['draw:tool', 'draw:select', 'draw:remove', 'draw:update'] as const) {
        host.onEmit(event, publish);
      }
      host.on('dblclick', () => {
        const selected = controllerRef.current?.selected();
        if (selected && TEXT_TOOLS.has(selected.tool) && aliveRef.current) {
          setTextRequest({ id: selected.id, tool: selected.tool, style: textStyleOf(selected) });
        }
      });

      if (tool) controller.setTool(tool);
      publish();
    })();

    return () => {
      cancelled = true;
    };
    // `tool` is here so that arming the first tool is what triggers the lazy
    // load; the effect no-ops once a controller exists and the tool is synced
    // by the effect below.
  }, [handleRef, containerRef, chartEpoch, storageKey, tool, publish]);

  useEffect(
    () => () => {
      controllerRef.current?.destroy();
      hostRef.current?.destroy();
      controllerRef.current = null;
      hostRef.current = null;
    },
    []
  );

  // -- keep the controller in step with props --------------------------------
  useEffect(() => {
    const controller = controllerRef.current;
    if (!controller) return;
    if (controller.getTool() !== tool) controller.setTool(tool);
  }, [tool]);

  useEffect(() => {
    controllerRef.current?.setOptions({ magnet });
    publish();
  }, [magnet, publish]);

  useEffect(() => {
    hostRef.current?.update({ candles, theme });
  }, [candles, theme]);

  // Lock and hide are properties of the whole cell's drawings, so they are
  // applied across every one rather than being a per-drawing field the reader
  // sets one at a time (the style bar's padlock does that separately).
  useEffect(() => {
    const controller = controllerRef.current;
    if (!controller) return;
    for (const drawing of controller.toJSON()) {
      if (drawing.locked !== locked || drawing.visible === !visible) {
        controller.update(drawing.id, { locked, visible });
      }
    }
  }, [locked, visible]);

  // A committed tool lands the toolbar back on the cursor — but only once the
  // controller has actually *taken* the armed tool and then cleared it (a real
  // placement). `stats.tool` mirrors the controller, and it lags the page's
  // `tool` by at least one render on every arm — and by the whole async engine
  // load on the first one. Without this confirmation guard the effect sees
  // `stats.tool === null` while `tool` is freshly set and disarms the tool
  // before it was ever placed, so no drawing tool ever engages.
  const toolConfirmed = useRef(false);
  useEffect(() => {
    // A fresh arm: forget any previous confirmation until the controller reports
    // it has this tool in hand.
    toolConfirmed.current = false;
  }, [tool]);
  useEffect(() => {
    if (tool !== null && stats.tool === tool) toolConfirmed.current = true;
    if (toolConfirmed.current && stats.tool === null && tool !== null) {
      latest.current.onToolDone();
    }
  }, [stats.tool, tool]);

  // -- actions ---------------------------------------------------------------
  const undo = useCallback(() => {
    controllerRef.current?.undo();
    publish();
  }, [publish]);

  const redo = useCallback(() => {
    controllerRef.current?.redo();
    publish();
  }, [publish]);

  const remove = useCallback(
    (all: boolean) => {
      const controller = controllerRef.current;
      if (!controller) return;
      if (all) controller.removeAll();
      else {
        const selected = controller.selected();
        if (selected) controller.remove(selected.id);
      }
      publish();
    },
    [publish]
  );

  const style = useCallback(
    (patch: { color?: string; lineWidth?: number; lineStyle?: string; locked?: boolean }) => {
      const controller = controllerRef.current;
      const selected = controller?.selected();
      if (!controller || !selected) return;
      // `locked` is a field on the drawing; colour, width and dash are style.
      // Splitting them here keeps the style bar from having to know that.
      const { locked: lock, ...rest } = patch;
      controller.update(selected.id, {
        style: rest as DrawingStyle,
        ...(lock === undefined ? {} : { locked: lock })
      });
      publish();
    },
    [publish]
  );

  const editSelectedText = useCallback(() => {
    const selected = controllerRef.current?.selected();
    if (!selected || !TEXT_TOOLS.has(selected.tool)) return;
    setTextRequest({ id: selected.id, tool: selected.tool, style: textStyleOf(selected) });
  }, []);

  const applyText = useCallback(
    (id: string, value: DrawTextStyle) => {
      const controller = controllerRef.current;
      if (!controller) return;
      const text = value.text.trim();
      // Cancelling out of a freshly placed, still-empty note leaves nothing
      // behind — an invisible drawing the reader cannot see but can still hit
      // is worse than no drawing at all.
      if (text === '') {
        controller.remove(id);
      } else {
        controller.update(id, {
          style: {
            text,
            color: value.color,
            fontSize: value.fontSize,
            fontWeight: value.bold ? 'bold' : 'normal',
            fontStyle: value.italic ? 'italic' : 'normal',
            background: value.background,
            backgroundColor: value.backgroundColor,
            border: value.border,
            borderColor: value.borderColor,
            wrap: value.wrap
          }
        });
      }
      setTextRequest(null);
      publish();
    },
    [publish]
  );

  const closeText = useCallback(() => setTextRequest(null), []);

  const armByShortcut = useCallback((event: KeyboardEvent): string | null => {
    const engine = engineRef.current;
    if (!engine) return null;
    return engine.matchDrawingShortcut(event);
  }, []);

  return {
    stats,
    selection,
    textRequest,
    undo,
    redo,
    remove,
    style,
    editSelectedText,
    applyText,
    closeText,
    armByShortcut
  };
}

function projectSelection(drawing: Drawing): DrawSelection {
  return {
    id: drawing.id,
    tool: drawing.tool,
    hasText: TEXT_TOOLS.has(drawing.tool),
    color: (drawing.style.color as string | undefined) ?? '#4f8cff',
    lineWidth: drawing.style.lineWidth ?? 1.5,
    lineStyle: drawing.style.lineStyle ?? 'solid',
    locked: drawing.locked === true
  };
}

function textStyleOf(drawing: Drawing): DrawTextStyle {
  const st = drawing.style;
  const color = st.color ?? '#e4e8f4';
  return {
    text: st.text ?? '',
    color,
    fontSize: st.fontSize ?? 14,
    bold: st.fontWeight === 'bold',
    italic: st.fontStyle === 'italic',
    background: st.background === true,
    // Deliberately not the chart's own background: the first time the reader
    // ticks "Background" the toggle has to visibly do something, and a plate
    // the same colour as what is behind it does not.
    backgroundColor: st.backgroundColor ?? '#434651',
    border: st.border === true,
    borderColor: st.borderColor ?? color,
    wrap: st.wrap === true
  };
}

function load(key: string): Drawing[] {
  if (typeof window === 'undefined') return [];
  try {
    const raw = window.localStorage.getItem(`${key}:draw`);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as Drawing[]) : [];
  } catch {
    return [];
  }
}

function save(key: string, drawings: Drawing[]): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(`${key}:draw`, JSON.stringify(drawings));
  } catch {
    // A full or blocked storage must not take the chart down with it.
  }
}
