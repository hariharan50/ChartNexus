import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { SERVER_CHART_THEME } from '../../app/lib/shared/charts/theme/tokens';

/**
 * Settings › Global › Call / Put Colour.
 *
 * The preference is implemented as four CSS custom properties and one
 * attribute selector, which makes the interesting failures *silent*: a
 * component that reaches for `--cn-bullish` where it means "call" keeps
 * working under the default palette and quietly contradicts every other
 * element under the inverted one. Nothing in the type system can catch that,
 * so the contract is pinned here instead.
 *
 * Two rules, and the second matters more than the first:
 *
 *   1. Inverting swaps call with put.
 *   2. Inverting changes NOTHING else — most of all not direction. A user who
 *      asked for red calls has not asked for green down-candles.
 */

const read = (path: string) => readFileSync(fileURLToPath(new URL(path, import.meta.url)), 'utf8');

const appCss = read('../../app/app.css');
const chartTokens = read('../../app/lib/shared/charts/theme/tokens.ts');

/** The body of the one `[data-callput='inverted']` rule. */
function invertedBlock(): string {
  const match = /:root\[data-callput='inverted'\]\s*\{([^}]*)\}/.exec(appCss);
  expect(match, "app.css must carry exactly one :root[data-callput='inverted'] rule").toBeTruthy();
  return match![1]!;
}

/** `--name: value` pairs declared in a block, comments stripped. */
function declarations(block: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const line of block.replace(/\/\*[\s\S]*?\*\//g, '').split(';')) {
    const match = /\s*(--[\w-]+)\s*:\s*(.+)/.exec(line);
    if (match) out[match[1]!] = match[2]!.trim();
  }
  return out;
}

describe('the call/put tokens', () => {
  it('default to this theme’s own direction colours', () => {
    // Declared as `var()` references rather than copied hexes, which is what
    // lets one declaration in `:root` serve all five themes.
    expect(appCss).toContain('--cn-call: var(--cn-bullish);');
    expect(appCss).toContain('--cn-put: var(--cn-bearish);');
  });

  it('carry a second, fixed pair for plotted series', () => {
    // A series colour is read against the other series, not against the panel,
    // so this pair deliberately does not follow the theme.
    expect(appCss).toMatch(/--cn-call-series:\s*#22c55e;/);
    expect(appCss).toMatch(/--cn-put-series:\s*#ef4444;/);
  });
});

describe('the inverted palette', () => {
  it('swaps both call/put pairs and nothing else', () => {
    const declared = declarations(invertedBlock());

    expect(declared).toEqual({
      '--cn-call': 'var(--cn-bearish)',
      '--cn-put': 'var(--cn-bullish)',
      '--cn-call-series': '#ef4444',
      '--cn-put-series': '#22c55e'
    });
  });

  it('leaves direction alone', () => {
    // The regression this whole split exists to prevent: inverting the
    // *market* tokens would turn every falling price green.
    const declared = declarations(invertedBlock());

    expect(declared['--cn-bullish']).toBeUndefined();
    expect(declared['--cn-bearish']).toBeUndefined();
  });

  it('is the only thing that reads the attribute', () => {
    // More than one rule on `data-callput` means the preference has grown a
    // second, undocumented effect somewhere down the file. Comments mentioning
    // the attribute are not rules, so this counts selectors.
    const selectors = appCss.replace(/\/\*[\s\S]*?\*\//g, '').match(/\[data-callput[^\]]*\]/g);

    expect(selectors).toHaveLength(1);
  });
});

describe('the chart theme', () => {
  it('binds call and put to the swappable tokens', () => {
    expect(chartTokens).toContain("call: '--cn-call-series'");
    expect(chartTokens).toContain("put: '--cn-put-series'");
  });

  it('binds up and down to the fixed direction tokens', () => {
    // Every chart that encodes a sign — advance/decline, net flow, a candle,
    // an IV-minus-HV bar — reads these, and they must not move.
    expect(chartTokens).toContain("up: '--cn-bullish'");
    expect(chartTokens).toContain("down: '--cn-bearish'");
  });

  it('gives the four roles four distinct colours on the server snapshot', () => {
    // SSR cannot read the document, so these are copied literals. A copy/paste
    // that collapsed call onto up would make the preference look broken on the
    // first paint only, which is the hardest kind of bug to catch by eye.
    const { call, put, up, down } = SERVER_CHART_THEME;

    expect(new Set([call, put, up, down]).size).toBe(4);
  });
});

describe('the Options Lab palette', () => {
  it('is no longer a module constant', () => {
    // `CALL_COLOR`/`PUT_COLOR` were imported by a dozen pages. A constant
    // cannot follow a preference, so re-exporting one would silently opt that
    // page out of the setting.
    const oiData = read('../../app/routes/terminal/options/open-interest/oi-data.ts');

    expect(oiData).not.toMatch(/export const (CALL|PUT)_COLOR/);
  });
});
