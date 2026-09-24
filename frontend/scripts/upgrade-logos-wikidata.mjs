/**
 * Replace the small marks with Wikidata's, where it has one we can trust.
 *
 * After `fetch-logos.mjs`, about sixty symbols are still stuck at 16-32px. They
 * are not failures of that script: those companies publish nothing bigger than
 * a legacy favicon, and their own sites are unreachable from a machine outside
 * India, so there is no larger file for an icon service to have cached. ITC,
 * Tata Steel, Bharti Airtel, M&M, ONGC and the whole Adani group are in that
 * set — names too prominent on the board to leave soft.
 *
 * Wikidata carries a logo (P154) for most listed companies, usually as SVG,
 * which is the best possible answer: sharp at every size and smaller than the
 * PNG it replaces.
 *
 * **The match is made on the official website (P856), never on the company
 * name.** Name matching is what produced Sun Microsystems for Sun Pharma and
 * United Airlines for United Spirits, and it would be worse here because a
 * Wikidata hit looks authoritative. The domains in `logo-domains.json` are
 * hand-verified, so joining on them inherits that verification instead of
 * re-opening the question.
 *
 * Two further guards, both of which caught a real error while this was written:
 *
 * * **Hosts are compared exactly, after dropping `www.`** — a suffix test let
 *   `techmahindra.com` answer for `mahindra.com`.
 * * **A domain claimed by more than one entity is skipped, not guessed.**
 *   `airtel.in` resolves to both Bharti Airtel and Tata Docomo, a brand Airtel
 *   absorbed, and Wikidata offers Tata Docomo's logo just as confidently. When
 *   the answer is ambiguous the existing small mark is kept — it is at least
 *   the right company.
 *
 *     node scripts/upgrade-logos-wikidata.mjs            # only what is small
 *     node scripts/upgrade-logos-wikidata.mjs --all      # reconsider everything
 *
 * Run `normalize-logos.py` afterwards; rasters arriving here are full size.
 */

import { readFile, readdir, unlink, writeFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const OUT = join(HERE, '..', 'public', 'logos');
const TABLE = join(HERE, 'logo-domains.json');
const MANIFEST = join(HERE, '..', 'app', 'lib', 'shared', 'ui', 'logo-manifest.json');

const SPARQL = 'https://query.wikidata.org/sparql';
const COMMONS = 'https://commons.wikimedia.org/wiki/Special:FilePath/';

/** Wikimedia asks automated clients to identify themselves. */
const UA = 'MarketCompass-logo-upgrade/1.0 (F&O terminal; contact: repository owner)';

/** Below this a mark is soft in a 22px avatar on a 2x display. */
const SHARP_PX = 64;

/** Raster width to request from Commons. Matches the normalize pass's cap. */
const RASTER_PX = 128;

/**
 * Domains per SPARQL request.
 *
 * Large on purpose, because the query below is an indexed lookup rather than a
 * scan. The first version of this filtered with `CONTAINS` over every item
 * holding both a website and a logo, which is priced per domain in the batch:
 * eight at a time already exceeded the public endpoint's timeout, and ten of
 * eleven batches came back as a timeout or a 502. Matching exact IRIs instead
 * answers eighty domains in about a second.
 */
const BATCH = 80;

/** Attempts per batch. The public endpoint sheds load rather than queueing. */
const ATTEMPTS = 3;

const TIMEOUT_MS = 60_000;

/** `www.example.com` and `example.com` are the same host; nothing else is. */
function hostOf(url) {
  try {
    return new URL(url).hostname.replace(/^www\./, '').toLowerCase();
  } catch {
    return null;
  }
}

/**
 * The URL spellings a site's `P856` may carry for one domain.
 *
 * Wikidata stores whatever the editor typed, so the same company appears as
 * `http://example.com`, `https://www.example.com/`, and everything between.
 * Enumerating the eight combinations turns a substring scan into an indexed
 * lookup, which is the difference between one second and a timeout.
 *
 * A site recorded with a path (`example.com/en-in/`) is missed by this and
 * falls through to the initials avatar — an acceptable trade for a query that
 * completes.
 */
function urlSpellings(domain) {
  const urls = [];
  for (const scheme of ['http', 'https']) {
    for (const prefix of ['', 'www.']) {
      for (const tail of ['', '/']) urls.push(`<${scheme}://${prefix}${domain}${tail}>`);
    }
  }
  return urls;
}

/**
 * The two Indian exchanges, in Wikidata's ids.
 *
 * A listing on either is what proves a candidate is the company this symbol
 * denotes. Only the NSE carries the ticker worth comparing — BSE codes are
 * numeric (`500470`) and could never equal an NSE symbol — so a BSE listing
 * counts as evidence of identity but never as a ticker match.
 */
const NSE = 'Q638740';
const BSE = 'Q638398';

/**
 * Candidate rows for a batch of domains, keyed by host.
 *
 * Returns every (entity, logo, ticker) row rather than picking a winner: the
 * choice needs the symbol, which this function does not have.
 *
 * The host comparison is redone here on the results even though the IRI list
 * was built from the same domains — reading the host back off each answer is
 * what guarantees a row cannot be credited to a domain it does not belong to.
 */
async function logosFor(domains) {
  const values = domains.flatMap(urlSpellings).join(' ');
  const query = `
    SELECT ?item ?itemLabel ?site ?logo ?listing ?exchange ?ticker WHERE {
      VALUES ?site { ${values} }
      ?item wdt:P856 ?site ; wdt:P154 ?logo .
      OPTIONAL {
        ?item p:P414 ?listing .
        ?listing ps:P414 ?exchange .
        VALUES ?exchange { wd:${NSE} wd:${BSE} }
        OPTIONAL { ?listing pq:P249 ?ticker }
      }
      SERVICE wikibase:label { bd:serviceParam wikibase:language "en" }
    }`;

  // POST, not GET: eighty domains expand to 640 IRIs, and that query in a URL
  // is rejected with 414 before it ever reaches the database.
  const response = await fetch(SPARQL, {
    method: 'POST',
    headers: {
      'User-Agent': UA,
      Accept: 'application/sparql-results+json',
      'Content-Type': 'application/x-www-form-urlencoded'
    },
    body: new URLSearchParams({ query, format: 'json' }),
    signal: AbortSignal.timeout(TIMEOUT_MS)
  });
  if (!response.ok) throw new Error(`SPARQL ${response.status}`);

  const wanted = new Set(domains);
  const byHost = new Map();

  for (const row of (await response.json()).results.bindings) {
    const host = hostOf(row.site.value);
    if (!host || !wanted.has(host)) continue;

    const rows = byHost.get(host) ?? [];
    rows.push({
      logo: row.logo.value,
      label: row.itemLabel?.value ?? null,
      listed: Boolean(row.listing?.value),
      onNse: row.exchange?.value?.endsWith(NSE) ?? false,
      ticker: row.ticker?.value ?? null
    });
    byHost.set(host, rows);
  }
  return byHost;
}

/**
 * The one logo that provably belongs to this NSE symbol, or a reason it does not.
 *
 * **Owning the domain is not enough.** `airtel.in` answers as Tata DoCoMo, a
 * brand Bharti Airtel absorbed and whose page kept the domain, and an earlier
 * version of this script shipped DoCoMo's logo for BHARTIARTL on exactly that
 * evidence. Company names are no help either — that is the derivation approach
 * the domain table exists to replace.
 *
 * What does settle it is the exchange listing. The symbols here are NSE
 * symbols, so the candidate must be listed on the NSE, and where Wikidata
 * records the ticker for that listing it must be this symbol. Tata DoCoMo has
 * no listing and is refused; Bokaro Steel Plant has none either, so `sail.co.in`
 * resolves to SAIL alone without needing an ambiguity rule to break the tie.
 *
 * The cost is real and accepted: correct companies whose entity simply lacks
 * exchange data — Indian Oil, Jubilant FoodWorks — are refused too, and keep
 * the smaller mark they already had. A soft logo is a blemish; the wrong
 * company's logo is a lie about which row you are reading.
 */
function verify(rows, symbol) {
  const listed = rows.filter((row) => row.listed);
  if (!listed.length) return { logo: null, why: 'no NSE or BSE listing recorded' };

  // Compare tickers only where an NSE ticker exists to compare. A company
  // recorded with a BSE listing alone has proved it is the listed Indian
  // company, which is the thing in doubt; its numeric code proves nothing more.
  const key = symbol.trim().toUpperCase();
  const tickered = listed.filter((row) => row.onNse && row.ticker);
  const usable = tickered.length
    ? tickered.filter((row) => row.ticker.trim().toUpperCase() === key)
    : listed;

  if (!usable.length) {
    const seen = [...new Set(tickered.map((row) => row.ticker))].join('/');
    return { logo: null, why: `NSE ticker is ${seen}, not ${key}` };
  }

  // Several entities can legitimately share one mark (a parent and a plant).
  // Distinct marks with nothing to choose between them is the unsafe case.
  const logos = [...new Set(usable.map((row) => row.logo))];
  if (logos.length > 1) return { logo: null, why: 'several different marks offered' };

  const winner = usable.find((row) => row.logo.toLowerCase().endsWith('.svg')) ?? usable[0];
  return { logo: winner.logo, label: winner.label, why: null };
}

async function download(fileUrl) {
  const name = decodeURIComponent(fileUrl.split('/').pop() ?? '');
  const svg = name.toLowerCase().endsWith('.svg');
  const url = `${COMMONS}${encodeURIComponent(name)}${svg ? '' : `?width=${RASTER_PX}`}`;

  const response = await fetch(url, {
    headers: { 'User-Agent': UA },
    redirect: 'follow',
    signal: AbortSignal.timeout(TIMEOUT_MS)
  });
  if (!response?.ok) return null;

  // The timeout aborts the stream, not just the handshake, so the body read
  // needs its own guard or one slow file ends the run.
  try {
    return { bytes: Buffer.from(await response.arrayBuffer()), ext: svg ? 'svg' : 'png' };
  } catch {
    return null;
  }
}

/** Current pixel width of a committed mark; Infinity for a vector. */
function widthOf(bytes, ext) {
  if (ext === 'svg') return Infinity;
  return bytes.length > 24 && bytes.subarray(1, 4).toString('latin1') === 'PNG'
    ? bytes.readUInt32BE(16)
    : 1;
}

async function main() {
  const all = process.argv.includes('--all');
  const table = JSON.parse(await readFile(TABLE, 'utf8'));
  const manifest = JSON.parse(await readFile(MANIFEST, 'utf8'));
  const present = new Set(await readdir(OUT).catch(() => []));

  // Which symbols are worth asking about: the soft ones, plus anything with no
  // mark at all, since Wikidata may know a company whose own site is dark.
  const candidates = [];
  for (const [symbol, domain] of Object.entries(table)) {
    const ext = manifest[symbol];
    if (!ext) {
      candidates.push([symbol, domain]);
      continue;
    }
    const bytes = await readFile(join(OUT, `${symbol}.${ext}`)).catch(() => null);
    if (!bytes) continue;
    if (all || widthOf(bytes, ext) < SHARP_PX) candidates.push([symbol, domain]);
  }

  const bySymbol = new Map(candidates);
  const domains = [...new Set(candidates.map(([, d]) => d))];

  const found = new Map();
  // Domains whose query never completed. Kept apart from domains Wikidata
  // answered about and had nothing for: reporting a timeout as "no logo" is a
  // lie that makes a transient outage look like a permanent absence.
  const unqueried = new Set();
  const batches = Math.ceil(domains.length / BATCH);

  for (let i = 0; i < domains.length; i += BATCH) {
    const slice = domains.slice(i, i + BATCH);
    const label = `batch ${i / BATCH + 1}/${batches}`;

    for (let attempt = 1; attempt <= ATTEMPTS; attempt += 1) {
      try {
        for (const [host, entry] of await logosFor(slice)) found.set(host, entry);
        break;
      } catch (error) {
        if (attempt === ATTEMPTS) {
          console.error(`  ${label} gave up: ${error.message}`);
          for (const domain of slice) unqueried.add(domain);
          break;
        }
        // Backing off matters more than retrying here: a 502 means the endpoint
        // is shedding load, and an immediate retry is just more of the load.
        await new Promise((resume) => setTimeout(resume, attempt * 5_000));
      }
    }
  }

  let upgraded = 0;
  const ambiguous = [];
  const unknown = [];
  const skipped = [];

  for (const [symbol, domain] of bySymbol) {
    const rows = found.get(domain);
    if (!rows) {
      (unqueried.has(domain) ? skipped : unknown).push(symbol);
      continue;
    }

    const entry = verify(rows, symbol);
    if (!entry.logo) {
      ambiguous.push(`${symbol} — ${entry.why}`);
      continue;
    }

    const file = await download(entry.logo);
    if (!file) {
      unknown.push(symbol);
      continue;
    }

    // A symbol that moves from PNG to SVG must not leave the old file behind:
    // the server types the response from the extension, so a stale sibling is
    // a coin-flip over which one a request resolves to.
    const previous = manifest[symbol];
    if (previous && previous !== file.ext && present.has(`${symbol}.${previous}`)) {
      await unlink(join(OUT, `${symbol}.${previous}`));
    }

    await writeFile(join(OUT, `${symbol}.${file.ext}`), file.bytes);
    manifest[symbol] = file.ext;
    upgraded += 1;
    console.warn(`  ${symbol.padEnd(12)} ${file.ext.padEnd(3)} ${entry.label ?? ''}`);
  }

  const sorted = Object.fromEntries(
    Object.entries(manifest).sort(([a], [b]) => a.localeCompare(b))
  );
  await writeFile(MANIFEST, `${JSON.stringify(sorted, null, 2)}\n`, 'utf8');

  console.warn(`\nupgraded ${upgraded} of ${bySymbol.size} considered`);
  if (ambiguous.length) {
    console.warn(`
refused ${ambiguous.length} that could not be verified against the symbol:`);
    for (const line of ambiguous) console.warn(`  ${line}`);
  }
  if (unknown.length) console.warn(`no Wikidata logo for ${unknown.length}: ${unknown.join(', ')}`);
  if (skipped.length) {
    console.warn(`\n${skipped.length} never queried — re-run to retry: ${skipped.join(', ')}`);
  }
}

await main();
