/**
 * The engine's public surface — the module the adapter reaches for behind a
 * dynamic `import()`.
 *
 * Keep this list small. Everything exported here is loaded on the reader's
 * first drawing interaction, and the point of the split is that a chart nobody
 * draws on never pays for any of it.
 */

export { DrawingController } from './DrawingController';
export type { AddInput, ControllerOptions } from './DrawingController';
export { Layer, PREVIEW_ID } from './Layer';
export { allTools, drawingShortcuts, get as getTool, has as hasTool } from './registry';
export type { ToolDef } from './registry';
export { matchDrawingShortcut, parseChord } from './shortcuts';
export { registerBuiltins } from './tools';
export { project } from './render';
export type {
  Bar,
  ChartDragEvent,
  ChartPointerEvent,
  Drawing,
  DrawingStyle,
  HitResult,
  HostChart,
  Point,
  Primitive,
  RenderContext
} from './types';
