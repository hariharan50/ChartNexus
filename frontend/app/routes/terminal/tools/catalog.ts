/**
 * The Tools catalogue — one entry per tool box on `/tools`.
 *
 * Every tool here is a placeholder for now (B1…B12). The names are deliberately
 * temporary: the grid, the routing and the open-a-tool path are what this
 * module pins down, so each tool can be built out one at a time by replacing
 * its entry's copy and giving it a real page, without touching the layout.
 */

/** The badge tints, cycled across the grid so neighbouring boxes differ. */
export type ToolTone = 'violet' | 'indigo' | 'emerald' | 'sky' | 'amber' | 'rose';

export interface ToolEntry {
  /** URL segment under `/tools`. */
  slug: string;
  /** Two-letter monogram shown in the badge. */
  code: string;
  /** Display name. Temporary until the tool is built. */
  name: string;
  /** One or two lines on what the tool will do. */
  description: string;
  tone: ToolTone;
}

const TONES: readonly ToolTone[] = ['violet', 'indigo', 'emerald', 'sky', 'amber', 'rose'];

/** The tools that exist. Built ones first; the rest are reserved slots. */
const BUILT: readonly ToolEntry[] = [
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
  }
];

/** The slots still to be filled, numbered from where the built ones stop. */
const RESERVED: readonly ToolEntry[] = Array.from({ length: 10 }, (_, index) => {
  const n = index + 3;
  return {
    slug: `b${n}`,
    code: `B${n}`,
    name: `B${n}`,
    description: 'Advanced graphical tool — not built yet. This slot is reserved for it.',
    tone: TONES[(BUILT.length + index) % TONES.length] as ToolTone
  };
});

/** Order is the grid order. */
export const TOOLS: readonly ToolEntry[] = [...BUILT, ...RESERVED];

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
  b2: 'straddle-chart'
};

/** Where a retired slug should land, or `undefined` if it was never a tool. */
export function retiredSlugTarget(slug: string | undefined): string | undefined {
  return slug ? RETIRED[slug] : undefined;
}
