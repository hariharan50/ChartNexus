/**
 * The tool registry.
 *
 * A tool is entirely described by this record: how many anchors it needs, what
 * it looks like, and how far the cursor is from it. Nothing else in the engine
 * knows one tool from another — the controller places anchors, the layer paints
 * and hit-tests, and both go through `ToolDef`. Adding a 44th tool is a
 * `register()` call and no edits anywhere else.
 */

import type { Pt } from './geometry';
import type { Drawing, DrawingStyle, Point, RenderContext } from './types';

export interface DrawArgs {
  /** Projected anchors in **device px** — already multiplied by `rc.dpr`. */
  pts: Pt[];
  drawing: Drawing;
  /** The drawing's style merged over the theme defaults. */
  style: DrawingStyle;
  rc: RenderContext;
}

export interface DistanceArgs {
  /** Projected anchors in **CSS px** — hit tolerances are CSS px. */
  pts: Pt[];
  drawing: Drawing;
  rc: RenderContext;
}

export interface ExpandContext {
  barSeconds: number;
  visibleBars: number;
}

export interface ToolDef {
  id: string;
  name: string;
  /** Required anchors. `0` means open-ended: collect until `finish()`. */
  points: number;
  /** e.g. `Alt+T`. Only five tools have one. */
  shortcut?: string;
  /** Inks on drag rather than on click. */
  freehand?: boolean;
  defaultStyle?: DrawingStyle;
  /** Turns the placed anchors into the drawing's real ones — see the position tools. */
  expand?(pts: Point[], ctx: ExpandContext): Point[];
  draw(ctx: CanvasRenderingContext2D, a: DrawArgs): void;
  distance(x: number, y: number, a: DistanceArgs): number;
}

const REGISTRY = new Map<string, ToolDef>();

export function register(def: ToolDef): void {
  REGISTRY.set(def.id, def);
}

export function has(id: string): boolean {
  return REGISTRY.has(id);
}

export function get(id: string): ToolDef {
  const def = REGISTRY.get(id);
  if (!def) throw new Error(`unknown drawing tool "${id}"`);
  return def;
}

/** For the UI, which must not hard-code the chords. */
export function drawingShortcuts(): Record<string, string> {
  const out: Record<string, string> = {};
  for (const def of REGISTRY.values()) if (def.shortcut) out[def.id] = def.shortcut;
  return out;
}

export function allTools(): ToolDef[] {
  return [...REGISTRY.values()];
}
