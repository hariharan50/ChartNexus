/**
 * Fails on a bare element selector in a CSS Module.
 *
 * This exists because of a real trap in this migration. Svelte compiled a
 * component's `<style>` block with a scoping hash, so `h1 { … }` inside
 * ComingSoon.svelte only ever matched that component's `h1`. CSS Modules
 * rewrites *class names only* — an element selector copied across verbatim
 * becomes a global rule that silently restyles every page in the app, and the
 * damage never shows up on the component you are currently porting.
 *
 * The rule: every selector must be anchored on a local class (`.panel h1`) or
 * be explicitly global (`:global(.mc-numeric)`).
 *
 * Anchoring is necessary but NOT sufficient, and this script cannot check the
 * rest. `.terminal nav { display: none }` passes here, yet it still hid the
 * settings sub-layout's <nav> — because a descendant selector reaches into
 * nested *components*, which Svelte's per-component scoping never did. When a
 * rule targets an element that another component might also render, give that
 * element its own class. The parity suite is what catches the ones that slip
 * through.
 */
import { globSync, readFileSync } from 'node:fs';
import { relative } from 'node:path';

const ROOT = new URL('..', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1');

const files = globSync('app/**/*.module.css', { cwd: ROOT });

// Inside these, the "selector" is not a selector.
const RAW_BLOCK = /^@(keyframes|font-face|counter-style|property|layer\s+[\w.]+;?$)/;
// These wrap real rules, so recurse into them rather than checking the prelude.
const WRAPPER = /^@(media|supports|container|layer|scope)\b/;

const problems = [];

for (const file of files) {
  const source = readFileSync(new URL(`../${file}`, import.meta.url), 'utf8').replace(
    /\/\*[\s\S]*?\*\//g,
    ''
  );

  let prelude = '';
  let line = 1;
  let preludeLine = 1;
  let rawDepth = 0;
  const stack = [];

  for (const char of source) {
    if (char === '\n') line += 1;

    if (char === '{') {
      const selector = prelude.trim();
      const isRaw = RAW_BLOCK.test(selector);
      const isWrapper = WRAPPER.test(selector);

      if (rawDepth === 0 && !isRaw && !isWrapper && selector) {
        for (const part of selector.split(',')) {
          const first = part.trim().split(/[\s>+~]/)[0] ?? '';
          if (!first) continue;
          if (first.startsWith('.') || first.startsWith(':global') || first.startsWith('&')) {
            continue;
          }
          problems.push({ file, line: preludeLine, selector: part.trim() });
        }
      }

      stack.push(isRaw);
      if (isRaw) rawDepth += 1;
      prelude = '';
      preludeLine = line;
    } else if (char === '}') {
      if (stack.pop()) rawDepth -= 1;
      prelude = '';
      preludeLine = line;
    } else if (char === ';') {
      prelude = '';
      preludeLine = line;
    } else {
      if (!prelude.trim() && char.trim()) preludeLine = line;
      prelude += char;
    }
  }
}

if (problems.length > 0) {
  console.error('Bare element selectors found in CSS Modules:\n');
  for (const { file, line, selector } of problems) {
    console.error(`  ${relative('.', file)}:${line}  ${selector}`);
  }
  console.error(
    '\nCSS Modules does not scope element selectors — these would apply app-wide.\n' +
      'Anchor each one on the component class, e.g. `h1` -> `.panel h1`.\n'
  );
  process.exit(1);
}

console.warn(`check-css-modules: ${files.length} files clean`);
