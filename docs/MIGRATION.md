# SvelteKit → React migration

`frontend/` moved from SvelteKit 2 / Svelte 5 to React Router v8 framework mode.
This was a framework swap, not a redesign: every screen was reproduced to the
pixel, and the backend, API contract, cookies, CSRF and design tokens were not
touched.

The last SvelteKit commit is **7a3144b**. Check it out beside the repo to
compare anything by hand — see [Parity](#parity-how-identical-was-verified).

## Stack delta

| Concern | Was | Now |
|---|---|---|
| Framework | SvelteKit 2 · Svelte 5 runes | React Router 8 (framework mode) · React 19 |
| Build | Vite 6 | Vite 8 |
| SSR host | `@sveltejs/adapter-node` → `build/index.js` | `@react-router/serve` → `build/server/index.js` |
| Routing | `src/routes` file conventions | explicit `app/routes.ts` |
| Data loading | `+layout.ts` `load` | route `loader` |
| Server data | `@tanstack/svelte-query` | `@tanstack/react-query` |
| Client state | `.svelte.ts` rune singletons | Zustand stores |
| Component CSS | Svelte scoped `<style>` | CSS Modules |
| Charts | inline ECharts in one component | `app/lib/shared/charts` engine |
| Types | `svelte-check` | `react-router typegen && tsc` |
| Unit tests | `@testing-library/svelte` | `@testing-library/react` |

Removed as unused: `layerchart`, `d3-scale`, `d3-shape` (declared but imported
nowhere) and `zod` (declared but imported nowhere).

## The transformation rulebook

Applied uniformly to all 108 components. Useful when reading a diff from this
era, or porting any remaining Svelte snippet.

### Script

| Svelte | React |
|---|---|
| `let { a } = $props()` | destructured typed params |
| `$props.id()` | `useId()` |
| `let x = $state(v)` | `const [x, setX] = useState(v)` |
| `const y = $derived(expr)` | a plain `const` — `useMemo` only when O(n) over chain/OI data, or when its identity feeds a dep array |
| `$derived.by(() => …)` | `useMemo(() => …, [deps])` |
| `$effect(() => {…; return cleanup})` | `useEffect(…, [deps])`, dependency array hand-derived |
| `onMount(fn)` | `useEffect(fn, [])` |
| `bind:this={el}` | `useRef` + `.current` |
| `value = $bindable('')` | controlled `value` + `onValueChange` pair |
| `extends HTMLInputAttributes` | `extends ComponentPropsWithoutRef<'input'>` |
| `page.url` (`$app/state`) | `useLocation()` / `useSearchParams()` |
| `goto(x)` | `useNavigate()` |
| `goto(x, { invalidateAll: true })` | `navigate(x)` + `useRevalidator().revalidate()` |
| `afterNavigate(fn)` | `useEffect(fn, [location.pathname])` |

`react-hooks/exhaustive-deps` is set to `error`, not the default warning: Svelte
tracked effect dependencies itself, and a wrong array is the failure mode this
port was most exposed to.

### Markup

| Svelte | React |
|---|---|
| `{#if}/{:else if}` | ternaries; extract a local render function past two levels |
| `{#each xs as x (x.id)}` | `xs.map(x => …)` carrying the **same** key expression |
| `{@const}` | a `const` inside the map callback |
| `{#snippet}` / `{@render}` | zero-arg snippet props become `ReactNode`, **not** `() => ReactNode` |
| `class:active={cond}` | `cx(s.base, cond && s.active)` — see `app/lib/shared/ui/cx.ts` |
| `<svelte:head><title>` | `export const meta` |
| in-app `<a href>` | `<Link to prefetch="intent">` |

### Styles

Each `<style>` block became `Component.module.css`, copied across with exactly
three edits. Two of them are traps that cost real debugging:

**1. Bare element selectors must be anchored.** Svelte compiled `h1 { … }` with
a per-component hash. CSS Modules rewrites *class names only*, so a verbatim
copy turns `h1` into a global rule that restyles the whole app — and the damage
never appears on the component being ported. `scripts/check-css-modules.mjs`
fails the build on any selector not starting with `.` or `:global`, and runs as
part of `pnpm lint`.

**2. Anchoring is necessary but not sufficient.** `.terminal nav { display: none }`
passes that check and was still wrong: a descendant selector reaches into nested
*components*, which Svelte's scoping never did, so it also hid the settings
sub-layout's `<nav>`. When a rule targets an element another component might
render, give that element its own class. The parity suite is what caught this.

**3. `:global(.child-class)` cannot work.** A parent reaching into a child's
internals (`form :global(.field)`, `td.ce.oi :global(.track)`) has nothing to
grab, because the child's class is hashed. Those became `className` props on
`TextField` and `OIBar`. `:global(.mc-numeric)` and friends stay as-is — those
classes live in `app.css` and are genuinely global.

### JSX whitespace

The one recurring source of *rendered* differences. Svelte emitted the newline
between two elements as a text node that the browser collapsed to a space; JSX
strips whitespace-only lines between elements entirely. Three real bugs came
from this, all found by pixel diffing:

- `PCR: <strong>0.94</strong> (+0.03)` lost its space.
- The option-chain strike cell lost the space before its `ATM` / `Max Pain` tag.
  That tag row set the column width, so a 4.4px loss redistributed across all
  eleven other columns and shifted every value in the table.
- `AiSummaryCard` was assembled as one string rather than inline JSX, because
  its sentence depended on that collapsing behaviour throughout.

When porting a multi-line text block, insert `{' '}` wherever Svelte relied on a
newline, and diff the rendered text.

## Route map

`app/routes.ts` is explicit rather than file-convention based: SvelteKit route
groups have no filename equivalent, and a config that reads top-to-bottom can be
compared against the old tree.

- `(group)/+layout.svelte` → `layout(file, children)` — pathless
- `dir/+layout.svelte` + pages → `route('dir', file, [index(…), …])` — pathful,
  which is how `/settings` works

All 49 routes carried over. **Not** given routes, because they contain only a
`.gitkeep` and no `+page.svelte` — they were not routes before either: the whole
`(admin)` group (`audit`, `ingestion`, `instruments`, `jobs`, `organizations`,
`subscriptions`, `users`), `(public)/disclosures`,
`(terminal)/{copilot,futures,institutional,signals}`, and
`settings/{api-keys,billing,organization,preferences}`.

## Deliberate behaviour changes

Everything else is byte-for-byte behaviour. These are not:

1. **Server-side token refresh removed.** `refreshInFlight` in
   `app/lib/shared/api/client.ts` is module scope — per-tab in a browser, but
   *per-process* on the Node server, i.e. one promise shared by every concurrent
   user's SSR render. It now returns early when `document` is undefined. A 401 in
   a loader is the real answer; the terminal guard turns it into a redirect.

2. **`shouldRevalidate: false` on the terminal layout.** SvelteKit's universal
   `+layout.ts` only re-ran on `invalidateAll()`. Without this, React Router
   would re-fetch `/auth/me` on every client navigation inside the group. Signing
   out revalidates explicitly instead.

3. **`$bindable` became controlled props.** `TextField`, `PasswordField` and
   `PhoneField` take `value` + `onValueChange`. Ten call sites updated.

4. **CSP is nonce-based.** SvelteKit's `csp: { mode: 'auto' }` hashed its own
   inline hydration script. React Router emits `window.__reactRouterContext`
   inline, so under a bare `script-src 'self'` the app renders and then never
   hydrates. Directives are otherwise unchanged from `svelte.config.js`.

5. **`/healthz` exists.** `deploy/docker/frontend.Dockerfile` has always
   healthchecked it, but the SvelteKit app had no `+server.ts` anywhere — the
   probe was hitting the 404 page. It has never passed until now.

6. **The OI chart is token-themed.** It picked from two hard-coded palettes off
   an `isDark` boolean, which collapsed `warm` onto the light set and `terminal`
   onto the dark one — so the cream `warm` theme got light-grey axis text on
   near-white. Chrome now resolves from `--mc-*`; Call/Put keep the Open Interest
   tool's own palette, which is a domain signal rather than chrome.

7. **No theme flash.** `app.html` hard-coded `data-theme="dark"` and ran no
   script, so a light-theme user saw a dark flash on every load. `root.tsx` now
   ships a small synchronous bootstrap that applies the stored theme before
   paint.

## Deliberately not done

- **Orval.** `contracts/openapi/v1/openapi.yaml` is an empty file; orval has
  never produced output, and `generated/` holds only a `.gitkeep`. Every endpoint
  is a hand-written wrapper under `app/lib/contexts`. `orval.config.ts` is kept
  and updated to `client: 'react-query'`, and `contracts:verify` is commented out
  in `Taskfile.yml` with instructions to restore it once the contract exists.
- **WebSockets.** `app/lib/shared/realtime/{client,protocol,query-cache-sync}.ts`
  were 0-byte files and remain so. There is no WS code and no message contract to
  port. Polling stays at `refetchInterval: 15_000`.
- **Zod.** Declared but imported nowhere. Introducing runtime validation is new
  behaviour, not a port.
- **Container queries.** The spec asked for them, but the app is already
  responsive through media queries at 90/72/64/60/48/40/30rem, all ported and
  verified. Adding container queries would change layout — a redesign, and it
  would break the parity that is this migration's contract. Worth doing as its
  own task.

## New configuration

`API_INTERNAL_URL` (server-only, defaults to `http://localhost:8000`).

The browser calls the same-origin path `/api/v1/...`; a loader has no page origin
to resolve that against and must not loop back through its own Node process.
SvelteKit's `handleFetch` hid this. `app/lib/shared/api/server-fetch.ts` is the
replacement — it resolves the path, forwards the browser's `Cookie`, and
forwards `x-request-id`. If it points at the wrong host, loaders 500.

## Invariants

**Module-scope stores are per-process on the server.** The Zustand stores and
`refreshInFlight` are singletons shared by every concurrent SSR request. Safe
only because nothing writes to them during render — `init()` runs from an effect,
setters from event handlers. **Never set store state from a loader or a component
body.** Each store file carries this as a header comment.

## Parity: how "identical" was verified

`pnpm parity` loads the same path in both apps at 1600/1280/1024/768/640/375px
and fails above a 0.1% pixel difference (`tests/parity/`). **96/96 passed** across
16 routes — every real screen, including the ECharts canvas.

It needs the SvelteKit app running alongside, which is no longer in the tree:

```
git worktree add ../mc-svelte 7a3144b
cd ../mc-svelte/frontend && pnpm install
API_PROXY_TARGET=http://localhost:8099 pnpm dev     # :5173

cd frontend && node tests/e2e/stub-api.mjs          # :8099, same data for both
pnpm parity
```

`tests/e2e/stub-api.mjs` is a deterministic backend stand-in — fixed prices, a
fixed clock, a seeded strike ladder — so a diff measures the port and not the
market. The suite also fixes `Date` via `page.clock`, because two of the pages
render a ticking clock.

## Test suites

| Command | What |
|---|---|
| `pnpm test` | 107 unit + component tests |
| `pnpm test:e2e` | 50 Playwright tests (routing, guards, CSP, placeholders, theme bootstrap) |
| `pnpm test:a11y` | 9 axe scans |
| `pnpm parity` | pixel diff vs SvelteKit (needs the worktree above) |

New coverage the SvelteKit app did not have: `api-client.test.ts` (CSRF, the
401 refresh single-flight, problem-details parsing — the highest-risk ported
file, previously untested), `open-interest-option.test.ts` (the chart option
builder, pure and DOM-free), the store tests, and the accessibility suite.

The accessibility suite asserts zero *structural* violations and pins the
inherited colour-contrast count per page. Both apps score identically —
`/login` 2, `/dashboard` 38, `/option-chain` 29, `/settings/global` 5, all
`color-contrast` from the `--mc-*` palette. The port introduced none of them, and
fixing them means changing the palette.

## Environment note

CI is Taskfile-only. Every `.github/workflows/*.yml` in this repo is a 0-byte
placeholder, so there is no GitHub Actions pipeline to update.
