/**
 * Pull each F&O company's mark into `public/logos/<SYMBOL>.(png|svg)`.
 *
 * Run occasionally; the output is committed. **The app never calls this at
 * runtime**, which is the whole point of the design:
 *
 * * a logo request per row would be ~200 third-party requests per board, on a
 *   page that polls every fifteen seconds;
 * * it would tell that third party which stocks every viewer is looking at;
 *   and
 * * it would break the moment the service did, or the developer went offline.
 *
 * Served from our own origin instead, the files are cached, private and
 * offline-safe, and anything missing falls back to the generated initials
 * avatar that carried this app before logos existed.
 *
 * **Domains are hand-maintained in `logo-domains.json` and that is deliberate.**
 * Deriving them from company names was tried and produces *confidently wrong*
 * logos: "Sun Pharma" resolves to Sun Microsystems, "United Spirits" to United
 * Airlines, "Indian Hotels" to a booking site, and three different public-sector
 * banks to the same placeholder. A wrong logo is far worse than a missing one —
 * it is a quiet lie about which company a row belongs to — so the mapping is
 * written down, and everything fetched is validated below.
 *
 * **Every source is tried and the *largest* mark wins.** Taking the first
 * source that answered shipped 110 of 179 logos at 32px or under, half of them
 * at 16 — soft at 22px on any modern display and visibly blurry on a retina
 * one. Favicons are small by definition; the good assets are the touch icon
 * and the web-app manifest, which sites publish at 180 to 512px. So this
 * measures what it gets and keeps the best.
 *
 *   node scripts/fetch-logos.mjs            # fill in anything missing
 *   node scripts/fetch-logos.mjs --force    # re-fetch everything
 *   node scripts/fetch-logos.mjs --upgrade  # re-fetch only what is small
 */

import { createHash } from 'node:crypto';
import { mkdir, readFile, readdir, writeFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const OUT = join(HERE, '..', 'public', 'logos');
const TABLE = join(HERE, 'logo-domains.json');

/**
 * Which symbols have a file, and in what format.
 *
 * Shipped so the avatar can decide *before* rendering rather than after a
 * failed request, and so it addresses the file correctly: the server types the
 * response from the extension, and an SVG served as `.png` is a broken image.
 */
const MANIFEST = join(HERE, '..', 'app', 'lib', 'shared', 'ui', 'logo-manifest.json');

/**
 * Placeholder bytes, by content hash.
 *
 * The icon services answer "I don't know this domain" with 200 and a grey
 * globe rather than a 404, so a naive fetcher stores that globe for every
 * domain it got wrong and the board fills with identical placeholders that
 * look deliberate. DuckDuckGo's is seeded; the rest are learnt at run time.
 */
const PLACEHOLDERS = new Set(['ab1fb25b83d4b333ea661a84bd298b2e']);

const UA =
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ' +
  '(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36';

/** Kept small: this is a courtesy scrape of free services, not a race. */
const CONCURRENCY = 6;

/** Below this an "icon" is an error page or a 1px spacer, not a logo. */
const MIN_BYTES = 120;

/**
 * What counts as sharp enough.
 *
 * The avatar draws at 22px and a 2x display needs 44 real pixels to render
 * that without softening. 64 is the next power of two up, and the threshold
 * `--upgrade` re-fetches below.
 */
const SHARP_PX = 64;

/** Past this, more pixels buy nothing at 22px and cost bandwidth. */
const ENOUGH_PX = 256;

const TIMEOUT_MS = 12_000;

async function get(url) {
  try {
    return await fetch(url, {
      headers: { 'User-Agent': UA },
      redirect: 'follow',
      signal: AbortSignal.timeout(TIMEOUT_MS)
    });
  } catch {
    return null;
  }
}

/**
 * Read a response body, or nothing.
 *
 * The timeout aborts the *stream*, not just the handshake, so a slow server
 * that answered its headers in time can still reject here — and an uncaught
 * rejection takes the whole run down two hundred domains in.
 */
async function bodyOf(response, as) {
  try {
    return as === 'text' ? await response.text() : Buffer.from(await response.arrayBuffer());
  } catch {
    return null;
  }
}

/* -- reading an image without decoding it ----------------------------------- */

/**
 * The mark's width in pixels, or `Infinity` for a vector.
 *
 * Parsed from the header rather than decoded: this only needs to *rank*
 * candidates, and pulling in an image library to compare two numbers would be
 * a dependency for arithmetic.
 */
function widthOf(bytes, contentType) {
  if (contentType.includes('svg')) return Infinity;

  // PNG: IHDR width is the four bytes at offset 16.
  if (bytes.length > 24 && bytes.subarray(1, 4).toString('latin1') === 'PNG') {
    return bytes.readUInt32BE(16);
  }

  // ICO: a directory of entries, each 16 bytes from offset 6, where a zero
  // width field means 256. Take the biggest — that is what a browser would.
  if (bytes.length > 22 && bytes.readUInt16LE(0) === 0 && bytes.readUInt16LE(2) === 1) {
    const count = bytes.readUInt16LE(4);
    let best = 0;
    for (let i = 0; i < count; i += 1) {
      const at = 6 + i * 16;
      if (at >= bytes.length) break;
      best = Math.max(best, bytes[at] === 0 ? 256 : bytes[at]);
    }
    return best;
  }

  // JPEG: walk the segments to the frame header.
  if (bytes.length > 4 && bytes[0] === 0xff && bytes[1] === 0xd8) {
    let at = 2;
    while (at + 9 < bytes.length && bytes[at] === 0xff) {
      const marker = bytes[at + 1];
      const length = bytes.readUInt16BE(at + 2);
      const isFrame = marker >= 0xc0 && marker <= 0xcf && ![0xc4, 0xc8, 0xcc].includes(marker);
      if (isFrame) return bytes.readUInt16BE(at + 7);
      at += 2 + length;
    }
  }

  // GIF, WebP, anything else: unknown. Ranked below a measured candidate
  // without being discarded, since it may be the only one on offer.
  return 1;
}

function extensionFor(contentType) {
  return contentType.includes('svg') ? 'svg' : 'png';
}

async function candidate(url) {
  const response = await get(url);
  if (!response?.ok) return null;

  // An HTML error page served as an icon is the commonest way a site says
  // "no" while answering 200.
  const type = response.headers.get('content-type') ?? '';
  if (type.includes('html') || (type.includes('text') && !type.includes('svg'))) return null;

  const bytes = await bodyOf(response, 'bytes');
  if (!bytes || bytes.length < MIN_BYTES) return null;
  const hash = createHash('md5').update(bytes).digest('hex');
  if (PLACEHOLDERS.has(hash)) return null;

  return { bytes, hash, ext: extensionFor(type), width: widthOf(bytes, type) };
}

/* -- where to look ---------------------------------------------------------- */

/**
 * Third-party icon services, which matter more than they look.
 *
 * Most of these companies' own sites are unreachable from a developer machine
 * outside India, so `wellKnownUrls` and the declared `<link>` icons simply time
 * out for them and the only mark on offer is whatever a service has cached.
 * That is why the big names sat at 16px: DuckDuckGo and Google both hand back
 * the tiny legacy favicon.
 *
 * Favicone resolves the *touch* icon server-side and answers at 256px, which is
 * where L&T, HDFC Bank and Tata Steel finally arrive at full resolution.
 *
 * `icon.horse` was tried here and rejected on purpose: for a domain it cannot
 * resolve it renders a grey tile with the company's first letter and serves it
 * with 200. That is a *generated* image, distinct per domain, so it cannot be
 * recognised by hash — it would quietly ship as a logo and defeat the whole
 * reason the domain table is hand-written. A missing mark is fine; the initials
 * avatar handles it, in this app's own type and colours.
 */
const serviceUrls = (domain) => [
  `https://favicone.com/${domain}?s=256`,
  `https://icons.duckduckgo.com/ip3/${domain}.ico`,
  `https://www.google.com/s2/favicons?domain=${domain}&sz=256`
];

const wellKnownUrls = (domain) => [
  `https://${domain}/apple-touch-icon.png`,
  `https://${domain}/apple-touch-icon-precomposed.png`,
  `https://${domain}/favicon.ico`
];

function resolveUrl(href, base) {
  try {
    return new URL(href, base).href;
  } catch {
    return null;
  }
}

/**
 * The icons a site declares in its own markup.
 *
 * This is where the large assets are: `apple-touch-icon` is 180px by
 * convention and a PWA manifest routinely carries 192 and 512. Both beat any
 * favicon, and neither is reliably discoverable by guessing a path.
 */
async function declaredIcons(domain) {
  const base = `https://${domain}/`;
  const response = await get(base);
  if (!response?.ok) return [];
  if (!(response.headers.get('content-type') ?? '').includes('html')) return [];

  // Only the head matters, and some of these home pages are 250KB.
  const body = await bodyOf(response, 'text');
  if (!body) return [];
  const html = body.slice(0, 200_000);
  const urls = [];

  for (const tag of html.match(/<link\b[^>]*>/gi) ?? []) {
    const rel = /rel=["']?([^"'>]+)/i.exec(tag)?.[1]?.toLowerCase() ?? '';
    const href = /href=["']?([^"'\s>]+)/i.exec(tag)?.[1];
    if (!href) continue;
    const absolute = resolveUrl(href, base);
    if (!absolute) continue;

    if (rel.includes('icon')) urls.push(absolute);
    if (rel.includes('manifest')) urls.push(...(await manifestIcons(absolute)));
  }
  return urls;
}

async function manifestIcons(url) {
  const response = await get(url);
  if (!response?.ok) return [];
  const body = await bodyOf(response, 'text');
  if (!body) return [];
  try {
    const manifest = JSON.parse(body);
    return (manifest.icons ?? [])
      .map((icon) => icon?.src)
      .filter(Boolean)
      .map((src) => resolveUrl(src, url))
      .filter(Boolean);
  } catch {
    return [];
  }
}

/**
 * Learn each service's placeholder by asking about domains that cannot exist.
 *
 * Two controls, not one, and both shaped like real domains: a service that
 * varies its placeholder by input would otherwise be learnt wrong from a single
 * sample, and some reject a bare `.invalid` outright instead of answering with
 * the stand-in they use in production.
 */
const CONTROLS = ['no-such-brand-55301b.com', 'not-a-company-7f3a2d.in'];

async function learnPlaceholders() {
  for (const control of CONTROLS) {
    for (const url of serviceUrls(control)) {
      const found = await candidate(url);
      if (found) PLACEHOLDERS.add(found.hash);
    }
  }
}

/**
 * The sharpest usable mark for one company.
 *
 * Every source is tried and the widest result wins, rather than the first that
 * answered. A candidate whose bytes another symbol has already claimed is
 * skipped rather than failing the symbol: that is a shared CDN placeholder
 * (`tcs.com` and `polycab.com` serve the same file) and the company may still
 * have a mark of its own further down the list.
 */
async function bestFor(domain, claimed) {
  const urls = [...serviceUrls(domain), ...wellKnownUrls(domain), ...(await declaredIcons(domain))];

  let best = null;
  let clashed = false;
  const seen = new Set();

  for (const url of urls) {
    if (seen.has(url)) continue;
    seen.add(url);
    if (best && best.width >= ENOUGH_PX) break;

    const found = await candidate(url);
    if (!found) continue;
    if (claimed.has(found.hash) && claimed.get(found.hash) !== domain) {
      clashed = true;
      continue;
    }
    if (!best || found.width > best.width) best = found;
  }
  return { best, clashed };
}

/* -- the run ----------------------------------------------------------------- */

async function existingWidths() {
  const widths = new Map();
  for (const name of await readdir(OUT).catch(() => [])) {
    const match = /^(.+)\.(png|svg)$/.exec(name);
    if (!match) continue;
    if (match[2] === 'svg') {
      widths.set(match[1], Infinity);
      continue;
    }
    widths.set(match[1], widthOf(await readFile(join(OUT, name)), 'image/png'));
  }
  return widths;
}

async function main() {
  const force = process.argv.includes('--force');
  const upgrade = process.argv.includes('--upgrade');
  const table = JSON.parse(await readFile(TABLE, 'utf8'));
  await mkdir(OUT, { recursive: true });
  await learnPlaceholders();

  const widths = await existingWidths();
  const wanted = Object.entries(table).filter(([symbol]) => {
    if (force) return true;
    const width = widths.get(symbol);
    if (width === undefined) return true;
    return upgrade && width < SHARP_PX;
  });

  const claimed = new Map();
  const missed = [];
  const collided = [];
  let saved = 0;
  let improved = 0;

  const queue = [...wanted];
  await Promise.all(
    Array.from({ length: CONCURRENCY }, async () => {
      for (;;) {
        const next = queue.shift();
        if (!next) return;
        const [symbol, domain] = next;

        const { best, clashed } = await bestFor(domain, claimed);
        if (!best) {
          if (clashed) collided.push(`${symbol} (${domain}) — only shared bytes on offer`);
          else missed.push(`${symbol} (${domain})`);
          continue;
        }

        // Never trade a sharp mark for a blurry one on a re-run.
        const had = widths.get(symbol);
        if (had !== undefined && had >= best.width) continue;

        claimed.set(best.hash, domain);
        await writeFile(join(OUT, `${symbol}.${best.ext}`), best.bytes);
        if (had === undefined) saved += 1;
        else improved += 1;
      }
    })
  );

  const have = Object.fromEntries(
    (await readdir(OUT))
      .filter((name) => /\.(png|svg)$/.test(name))
      .map((name) => [name.replace(/\.(png|svg)$/, ''), name.slice(name.lastIndexOf('.') + 1)])
      .sort(([a], [b]) => a.localeCompare(b))
  );
  await writeFile(MANIFEST, `${JSON.stringify(have, null, 2)}\n`, 'utf8');

  const count = Object.keys(have).length;
  const total = Object.keys(table).length;
  console.warn(`fetched ${saved} new, sharpened ${improved}, of ${wanted.length} attempted`);
  console.warn(
    `manifest: ${count} of ${total} have a logo, ${total - count} fall back to initials`
  );
  report('unresolved — fix the domain in logo-domains.json', missed);
  report('only shared bytes — a CDN placeholder, not a logo', collided);
}

function report(title, entries) {
  if (entries.length === 0) return;
  console.warn(`\n${entries.length} ${title}:`);
  for (const entry of entries.sort()) console.warn(`  ${entry}`);
}

await main();
