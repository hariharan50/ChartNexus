import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';
import { stubTradeBuddy } from '../e2e/trade-buddy-fixtures';

/**
 * Automated accessibility checks over the screens that carry real content.
 *
 * The SvelteKit app declared `axe-core` and reserved this directory but never
 * filled it. The migration is the cheapest moment to fill it: the markup was
 * just rewritten, so a regression introduced by the port shows up here rather
 * than months later.
 *
 * ## Why colour-contrast is measured, not asserted to zero
 *
 * Running this against both apps gives byte-identical results — `/login` 2,
 * `/dashboard` 38, `/option-chain` 29, `/settings/global` 5, every one of them
 * `color-contrast`. They come from the `--cn-*` palette in app.css, which the
 * migration copied unchanged, so they are inherited design debt rather than
 * anything the port did.
 *
 * Failing the build on them would mean either changing the palette — a redesign
 * this migration explicitly is not — or deleting the check. Instead the count is
 * pinned per page: it cannot grow without someone updating the number, and the
 * numbers are the to-do list for a separate contrast pass.
 */

/** Everything except contrast must be clean. */
const STRUCTURAL_TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'];

interface PageCase {
  path: string;
  name: string;
  signedIn: boolean;
  /**
   * Run before the page loads, for a screen whose content arrives through
   * client-side queries rather than a server loader.
   *
   * Without it such a page is scanned empty — no table rows, no list items,
   * no populated cards — which is the markup least likely to have a problem.
   */
  prepare?: (page: Page) => Promise<void>;
  /**
   * Remaining colour-contrast nodes.
   *
   * These were inherited from the SvelteKit app and ran to ~105 nodes. Raising
   * `--cn-text-subtle` to clear AA on all four themes cleared about ninety of
   * them; what is left is a handful of other token pairs, page by page.
   */
  contrastBudget: number;
}

const PAGES: PageCase[] = [
  // Budget 0, unlike every page below it: the landing page is new markup on a
  // new palette, so it carries none of the inherited debt and has no excuse.
  { path: '/', name: 'landing', signedIn: false, contrastBudget: 0 },
  { path: '/login', name: 'sign in', signedIn: false, contrastBudget: 2 },
  { path: '/register', name: 'register', signedIn: false, contrastBudget: 3 },
  { path: '/dashboard', name: 'dashboard', signedIn: true, contrastBudget: 2 },
  { path: '/advanced-dashboard', name: 'advanced dashboard', signedIn: true, contrastBudget: 5 },
  { path: '/option-chain', name: 'option chain', signedIn: true, contrastBudget: 9 },
  { path: '/options', name: 'options analytics', signedIn: true, contrastBudget: 2 },
  { path: '/options/open-interest', name: 'open interest', signedIn: true, contrastBudget: 1 },
  // None of the three come from this page's own markup. One is the terminal
  // shell's user avatar (white on blue, 3.2:1), which every signed-in page
  // here carries; the other two are the shared primary `Button` (white on the
  // brand orange, 3.79:1), which this screen simply uses twice — Save levels
  // and Save settings. Fixing either means changing the palette or the shared
  // component, which is a separate pass, so the number is pinned here as the
  // to-do rather than hidden behind a button style of this page's own.
  {
    path: '/tools/trade-buddy',
    name: 'trade buddy',
    signedIn: true,
    contrastBudget: 3,
    // This page reads everything through react-query in the browser, and the
    // production build the suite runs has no `/api` proxy — so without the
    // fixtures it would be scanned with every panel in its empty state.
    prepare: stubTradeBuddy
  },
  { path: '/settings/global', name: 'global settings', signedIn: true, contrastBudget: 2 },
  { path: '/settings/profile', name: 'personal info', signedIn: true, contrastBudget: 1 }
];

async function scan(page: Page) {
  return new AxeBuilder({ page }).withTags(STRUCTURAL_TAGS).analyze();
}

for (const { path, name, signedIn, contrastBudget, prepare } of PAGES) {
  test(`${name} is accessible`, async ({ page, context, baseURL }) => {
    if (signedIn) {
      await context.addCookies([
        { name: 'cn_session', value: 'test', url: baseURL ?? 'http://localhost:4173' }
      ]);
    }
    if (prepare) await prepare(page);

    await page.goto(path, { waitUntil: 'networkidle' });
    const { violations } = await scan(page);

    const structural = violations.filter((v) => v.id !== 'color-contrast');
    // Name the offending selectors in the failure — a bare count is useless.
    const summary = structural.map(
      (v) => `${v.id} (${v.impact}): ${v.nodes.map((n) => n.target.join(' ')).join(', ')}`
    );
    expect(summary, summary.join('\n')).toEqual([]);

    const contrastFailures = violations
      .filter((v) => v.id === 'color-contrast')
      .flatMap((v) => v.nodes);
    // Name the offending selectors here too. A bare count tells you the budget
    // moved but not which pair to fix, which is most of the work.
    const offenders = contrastFailures
      .map(
        (node) => `  ${node.target.join(' ')} — ${node.failureSummary?.split('\n').at(-1) ?? ''}`
      )
      .join('\n');
    expect(
      contrastFailures.length,
      `Inherited contrast debt on ${path} changed. If a palette fix reduced it, ` +
        `lower the budget; if new markup added to it, use an existing token pair.\n${offenders}`
    ).toBeLessThanOrEqual(contrastBudget);
  });
}
