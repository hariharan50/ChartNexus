/**
 * Chord parsing for the five tools that have one.
 *
 * The hard rule here is that a bare letter never arms a tool. Bare letters
 * belong to the chart and to the app around it — and to the reader, who may be
 * typing into something this listener cannot see. Requiring a modifier is what
 * makes a global keydown listener safe to install at all.
 */

import { drawingShortcuts } from './registry';
import { registerBuiltins } from './tools';

export interface Chord {
  key: string;
  alt: boolean;
  ctrl: boolean;
  shift: boolean;
}

export function parseChord(chord: string): Chord {
  const parts = chord.split('+').map((p) => p.trim().toLowerCase());
  return {
    key: parts[parts.length - 1] ?? '',
    alt: parts.includes('alt'),
    ctrl: parts.includes('ctrl') || parts.includes('control'),
    shift: parts.includes('shift')
  };
}

export interface ChordEvent {
  key: string;
  altKey: boolean;
  ctrlKey: boolean;
  metaKey: boolean;
  shiftKey: boolean;
}

/** The tool a keystroke arms, or `null`. */
export function matchDrawingShortcut(event: ChordEvent): string | null {
  if (!event.altKey && !event.ctrlKey && !event.metaKey) return null;
  registerBuiltins();
  const key = event.key.toLowerCase();
  for (const [tool, chord] of Object.entries(drawingShortcuts())) {
    const want = parseChord(chord);
    if (
      want.key === key &&
      want.alt === event.altKey &&
      want.ctrl === (event.ctrlKey || event.metaKey) &&
      want.shift === event.shiftKey
    ) {
      return tool;
    }
  }
  return null;
}
