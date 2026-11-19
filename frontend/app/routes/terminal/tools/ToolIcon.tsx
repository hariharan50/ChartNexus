import type { ReactNode } from 'react';

/**
 * The glyph in each Tools box, drawn for what the tool actually shows.
 *
 * Inline SVG in the house icon style (24-unit grid, round 1.75 strokes,
 * `currentColor`), so it inherits the badge's white and needs no asset
 * pipeline. Keyed by slug: a tool without a glyph falls back to its monogram
 * rather than an empty tile.
 */
const GLYPHS: Readonly<Record<string, ReactNode>> = {
  // A delta (the first Greek anyone reads) over gamma's bell-shaped curve.
  'option-greeks': (
    <>
      <path d="M12 3.5 6.5 13h11z" />
      <path d="M3 20.5c4 0 5.5-4.5 9-4.5s5 4.5 9 4.5" />
    </>
  ),
  // The straddle's V-shaped payoff under a price line on chart axes.
  'straddle-chart': (
    <>
      <path d="M3.5 3.5v17h17" />
      <path d="M7 10l5 7 5-7" />
      <path d="M7 6.5c1.7-1.5 3 .8 5-.3s3.3-1.7 5-.2" />
    </>
  ),
  // The payoff V being replayed: a V beside a replay arrow, over a P&L baseline.
  'straddle-pnl': (
    <>
      <path d="M2.5 5.5l4.5 8 4.5-8" />
      <path d="M2.5 18.5h9" />
      <path d="M14.5 14a3.75 3.75 0 1 0 1.1-2.65" />
      <path d="M15.6 8.85v2.5h2.5" />
    </>
  ),
  // A bell on a marked price level: the alert when a level is hit.
  'trade-buddy': (
    <>
      <path d="M6.5 15.5V11a5.5 5.5 0 0 1 11 0v4.5l1.5 2H5z" />
      <path d="M10.2 20a2 2 0 0 0 3.6 0" />
      <path d="M12 3.5v2" />
      <path d="M2.5 11h2M19.5 11h2" />
    </>
  )
};

export function ToolIcon({ slug, fallback }: { slug: string; fallback: string }) {
  const glyph = GLYPHS[slug];
  if (!glyph) return <>{fallback}</>;
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="24"
      height="24"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      data-tool-icon={slug}
    >
      {glyph}
    </svg>
  );
}
