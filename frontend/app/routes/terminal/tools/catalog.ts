/**
 * The Tools catalogue — one entry per tool box on `/tools`.
 *
 * Only built tools appear. The grid used to pad itself out to twelve with
 * generated `B4`…`B12` placeholders, which advertised nine tools that did not
 * exist and gave a reader nine dead ends to find. A tool earns its box by
 * being built: add it to `BUILT`, give it a route, and retire its old slug
 * below if it ever had one.
 */

/** The badge tints. Neighbouring boxes should not share one. */
export type ToolTone = 'violet' | 'indigo' | 'emerald' | 'sky' | 'amber' | 'rose';

export interface ToolEntry {
  /** URL segment under `/tools`. */
  slug: string;
  /** Two-letter monogram shown in the badge. */
  code: string;
  /** Display name. */
  name: string;
  /** One or two lines on what the tool does. */
  description: string;
  tone: ToolTone;
}

/** Order is the grid order. */
export const TOOLS: readonly ToolEntry[] = [
  {
    slug: 'option-greeks',
    code: 'OG',
    name: 'Option Greeks',
    description: 'Historical IV, Delta, Theta, Vega and Gamma charts for the at-the-money contract',
    tone: 'violet'
  },
  {
    slug: 'straddle-chart',
    code: 'SC',
    name: 'Straddle Chart',
    description:
      'Rolling at-the-money straddle with spot and the synthetic futures forward overlaid',
    tone: 'emerald'
  },
  {
    slug: 'straddle-pnl',
    code: 'SP',
    name: 'Straddle PnL Simulator',
    description:
      'Replays a short at-the-money straddle that re-strikes as the market moves, with its running P&L and trade log',
    tone: 'sky'
  }
];

export function toolBySlug(slug: string | undefined): ToolEntry | undefined {
  return TOOLS.find((tool) => tool.slug === slug);
}

/**
 * Slugs that used to exist, and where they went.
 *
 * A reserved slot gets a real name the moment it is built, which retires its
 * `b<n>` slug — and an open tab, a bookmark or a back button still points at
 * the old one. Redirecting costs a line and is the difference between landing
 * on the tool and landing on a 404. Entries stay here permanently: there is no
 * date after which someone's bookmark stops being their bookmark.
 */
const RETIRED: Readonly<Record<string, string>> = {
  b1: 'option-greeks',
  b2: 'straddle-chart',
  b3: 'straddle-pnl'
};

/** Where a retired slug should land, or `undefined` if it was never a tool. */
export function retiredSlugTarget(slug: string | undefined): string | undefined {
  return slug ? RETIRED[slug] : undefined;
}
