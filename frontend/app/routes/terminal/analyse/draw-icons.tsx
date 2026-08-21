/**
 * One glyph per drawing tool, as a literal miniature of what the tool draws.
 *
 * A rail of forty near-identical line drawings is only navigable if each icon
 * is a picture of its own result — the trend-line glyph is a diagonal with two
 * dots on it, the channel glyph is two parallels, the fib glyph is four stacked
 * horizontals. Anything more abstract and the reader is back to reading labels.
 *
 * Kept as one keyed module rather than forty files: these are two or three
 * paths each, they are only ever reached through `drawToolIcon`, and forty
 * one-export files would bury the shared `icons/` directory.
 */

import type { ReactNode } from 'react';

const PATHS: Record<string, ReactNode> = {
  cursor: (
    <>
      <line x1="12" y1="3" x2="12" y2="21" />
      <line x1="3" y1="12" x2="21" y2="12" />
    </>
  ),
  trend: (
    <>
      <line x1="6" y1="18" x2="18" y2="6" />
      <circle cx="5" cy="19" r="1.6" fill="currentColor" stroke="none" />
      <circle cx="19" cy="5" r="1.6" fill="currentColor" stroke="none" />
    </>
  ),
  ray: (
    <>
      <line x1="5" y1="19" x2="21" y2="3" />
      <circle cx="5" cy="19" r="1.6" fill="currentColor" stroke="none" />
    </>
  ),
  extended: (
    <>
      <line x1="3" y1="21" x2="21" y2="3" />
      <circle cx="9" cy="15" r="1.6" fill="currentColor" stroke="none" />
      <circle cx="15" cy="9" r="1.6" fill="currentColor" stroke="none" />
    </>
  ),
  arrow: (
    <>
      <line x1="5" y1="19" x2="17" y2="7" />
      <path d="M12 6h6v6" />
    </>
  ),
  hline: (
    <>
      <line x1="3" y1="12" x2="21" y2="12" />
      <circle cx="12" cy="12" r="1.6" fill="currentColor" stroke="none" />
    </>
  ),
  hray: (
    <>
      <line x1="8" y1="12" x2="21" y2="12" />
      <circle cx="7" cy="12" r="1.6" fill="currentColor" stroke="none" />
    </>
  ),
  vline: (
    <>
      <line x1="12" y1="3" x2="12" y2="21" />
      <circle cx="12" cy="12" r="1.6" fill="currentColor" stroke="none" />
    </>
  ),
  cross: (
    <>
      <line x1="3" y1="12" x2="21" y2="12" />
      <line x1="12" y1="3" x2="12" y2="21" />
      <circle cx="12" cy="12" r="1.6" fill="currentColor" stroke="none" />
    </>
  ),
  channel: (
    <>
      <line x1="4" y1="16" x2="20" y2="6" />
      <line x1="4" y1="20" x2="20" y2="10" />
    </>
  ),
  fibchannel: (
    <>
      <line x1="4" y1="18" x2="20" y2="8" />
      <line x1="4" y1="14" x2="20" y2="4" />
      <line x1="4" y1="21" x2="20" y2="11" opacity="0.55" />
    </>
  ),
  fib: (
    <>
      <line x1="3" y1="5" x2="21" y2="5" />
      <line x1="3" y1="10" x2="21" y2="10" />
      <line x1="3" y1="15" x2="21" y2="15" />
      <line x1="3" y1="20" x2="21" y2="20" />
    </>
  ),
  fibtime: (
    <>
      <line x1="4" y1="4" x2="4" y2="20" />
      <line x1="7" y1="4" x2="7" y2="20" />
      <line x1="12" y1="4" x2="12" y2="20" />
      <line x1="20" y1="4" x2="20" y2="20" />
    </>
  ),
  fibfan: (
    <>
      <line x1="4" y1="20" x2="21" y2="4" />
      <line x1="4" y1="20" x2="21" y2="11" />
      <line x1="4" y1="20" x2="21" y2="18" />
    </>
  ),
  rect: <rect x="4" y="6" width="16" height="12" rx="1" />,
  rotrect: <path d="M3 14l6-8 12 4-6 8z" />,
  ellipse: <ellipse cx="12" cy="12" rx="9" ry="6" />,
  circle: <circle cx="12" cy="12" r="8" />,
  triangle: <path d="M12 5l8 14H4z" />,
  path: <path d="M3 18l5-7 4 4 4-8 5 5" />,
  polyline: <path d="M4 18l4-9 6 3 6-7-2 14z" />,
  arc: <path d="M4 18a12 12 0 0 1 16-8" />,
  curve: <path d="M4 18c5 0 5-12 16-12" />,
  dcurve: <path d="M3 16c3 0 3-8 6-8s3 8 6 8 3-8 6-8" />,
  cyclic: (
    <>
      <line x1="5" y1="4" x2="5" y2="20" strokeDasharray="3 3" />
      <line x1="12" y1="4" x2="12" y2="20" strokeDasharray="3 3" />
      <line x1="19" y1="4" x2="19" y2="20" strokeDasharray="3 3" />
    </>
  ),
  timecycle: (
    <>
      <path d="M4 17a4 4 0 0 1 8 0" />
      <path d="M12 17a4 4 0 0 1 8 0" />
      <line x1="3" y1="17" x2="21" y2="17" />
    </>
  ),
  sine: <path d="M3 12c3-9 6 9 9 0s6-9 9 0" />,
  long: (
    <>
      <rect x="4" y="5" width="16" height="6" rx="1" />
      <rect x="4" y="13" width="16" height="6" rx="1" opacity="0.5" />
      <line x1="4" y1="12" x2="20" y2="12" />
    </>
  ),
  short: (
    <>
      <rect x="4" y="5" width="16" height="6" rx="1" opacity="0.5" />
      <rect x="4" y="13" width="16" height="6" rx="1" />
      <line x1="4" y1="12" x2="20" y2="12" />
    </>
  ),
  forecast: (
    <>
      <path d="M4 18l7-7" strokeDasharray="3 3" />
      <path d="M11 11l4 4 6-9" />
    </>
  ),
  measure: (
    <>
      <rect x="4" y="5" width="16" height="14" rx="1" />
      <line x1="12" y1="7" x2="12" y2="17" />
      <path d="M9 14l3 3 3-3" />
    </>
  ),
  pricerange: (
    <>
      <line x1="12" y1="4" x2="12" y2="20" />
      <path d="M8 8l4-4 4 4" />
      <path d="M8 16l4 4 4-4" />
    </>
  ),
  daterange: (
    <>
      <line x1="4" y1="12" x2="20" y2="12" />
      <path d="M8 8l-4 4 4 4" />
      <path d="M16 8l4 4-4 4" />
    </>
  ),
  text: (
    <>
      <path d="M5 6h14" />
      <line x1="12" y1="6" x2="12" y2="19" />
    </>
  ),
  pricelabel: (
    <>
      <path d="M3 12l4-4h13v8H7z" />
      <line x1="11" y1="12" x2="16" y2="12" />
    </>
  ),
  callout: (
    <>
      <rect x="7" y="4" width="14" height="10" rx="2" />
      <path d="M10 14l-6 6" />
    </>
  ),
  flag: (
    <>
      <line x1="6" y1="3" x2="6" y2="21" />
      <path d="M6 4h12l-3 4 3 4H6z" />
    </>
  ),
  arrowup: (
    <>
      <line x1="12" y1="20" x2="12" y2="6" />
      <path d="M6 12l6-6 6 6" />
    </>
  ),
  arrowdown: (
    <>
      <line x1="12" y1="4" x2="12" y2="18" />
      <path d="M6 12l6 6 6-6" />
    </>
  ),
  brush: (
    <>
      <path d="M4 20c4 0 2-5 6-9l5-5 3 3-5 5c-4 4-9 2-9 6z" />
    </>
  ),
  highlighter: (
    <>
      <path d="M5 16l8-8 4 4-8 8H5z" />
      <line x1="4" y1="21" x2="20" y2="21" strokeWidth="2.5" />
    </>
  ),
  magnet: (
    <>
      <path d="M6 4v8a6 6 0 0 0 12 0V4" />
      <line x1="6" y1="9" x2="10" y2="9" />
      <line x1="14" y1="9" x2="18" y2="9" />
    </>
  ),
  undo: (
    <>
      <path d="M4 10h10a5 5 0 0 1 0 10H9" />
      <path d="M8 6l-4 4 4 4" />
    </>
  ),
  redo: (
    <>
      <path d="M20 10H10a5 5 0 0 0 0 10h5" />
      <path d="M16 6l4 4-4 4" />
    </>
  ),
  trash: (
    <>
      <path d="M4 7h16" />
      <path d="M9 7V5h6v2" />
      <path d="M6 7l1 13h10l1-13" />
    </>
  ),
  lock: (
    <>
      <rect x="5" y="11" width="14" height="9" rx="2" />
      <path d="M8 11V8a4 4 0 0 1 8 0v3" />
    </>
  ),
  unlock: (
    <>
      <rect x="5" y="11" width="14" height="9" rx="2" />
      <path d="M8 11V8a4 4 0 0 1 7-2.6" />
    </>
  ),
  eye: (
    <>
      <path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z" />
      <circle cx="12" cy="12" r="3" />
    </>
  ),
  eyeoff: (
    <>
      <path d="M4 4l16 16" />
      <path d="M9.5 5.6A9.7 9.7 0 0 1 12 5c6 0 10 7 10 7a17 17 0 0 1-3.3 4" />
      <path d="M6 8a17 17 0 0 0-4 4s4 7 10 7a9.6 9.6 0 0 0 4-.9" />
    </>
  ),
  /** Fallback for a key with no glyph — a plain dot, so nothing renders empty. */
  default: <circle cx="12" cy="12" r="3" />
};

export function drawToolIcon(iconKey: string, size = 20): ReactNode {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {PATHS[iconKey] ?? PATHS.default}
    </svg>
  );
}
