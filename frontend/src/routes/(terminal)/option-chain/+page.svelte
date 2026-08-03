<script lang="ts">
  import { optionChainForExpiryQuery } from '$contexts/market-data/queries.svelte';
  import { metrics } from '$contexts/market-data/derive';
  import { formatInt, formatPrice } from '$shared/formatting/numbers';
  import IconClock from '$shared/ui/icons/IconClock.svelte';
  import IconChart from '$shared/ui/icons/IconChart.svelte';
  import IconChevronDown from '$shared/ui/icons/IconChevronDown.svelte';
  import {
    toStrikes,
    atmIndex,
    windowAround,
    maxOi,
    volumeRanks,
    topVolume,
    oiChangePct,
    compactIndian,
    signedPct,
    expiryLabel,
    daysAwayLabel,
    num,
    STRIKE_COUNTS,
    type StrikeCount,
    type Leg
  } from './chain-model';
  import BuildupBadge from './components/BuildupBadge.svelte';
  import OIBar from './components/OIBar.svelte';
  import VolCell from './components/VolCell.svelte';

  // --- instrument catalog --------------------------------------------------
  const CATALOG = [
    { id: 1, short: 'NIFTY', badge: '50', symbol: 'NIFTY' },
    { id: 2, short: 'SENSEX', badge: 'BSE', symbol: 'SENSEX' },
    { id: 3, short: 'BANKNIFTY', badge: 'BNK', symbol: 'BANKNIFTY' }
  ];

  let idx = $state(0);
  let selectedExpiry = $state<string | undefined>(undefined);
  let strikeCount = $state<StrikeCount>(5);

  const instrument = $derived(CATALOG[idx] ?? CATALOG[0]!);

  function cycle(delta: number) {
    idx = (idx + delta + CATALOG.length) % CATALOG.length;
    selectedExpiry = undefined; // the previous expiry may not exist on the new instrument
  }

  // --- data ----------------------------------------------------------------
  const chainQ = optionChainForExpiryQuery(
    () => instrument.symbol,
    () => selectedExpiry
  );

  const chain = $derived($chainQ.data);
  const loading = $derived($chainQ.isLoading);
  const refreshing = $derived($chainQ.isFetching);

  const strikes = $derived(chain ? toStrikes(chain) : []);
  const spot = $derived(chain ? num(chain.spot_price) : undefined);
  const spotChange = $derived(chain ? num(chain.change_percent) : undefined);
  const future = $derived(chain ? num(chain.future_price) : undefined);

  const atmIdx = $derived(atmIndex(strikes, spot, chain ? num(chain.atm_strike) : undefined));
  const atmStrike = $derived(atmIdx >= 0 ? strikes[atmIdx]?.strike : undefined);
  const visible = $derived(windowAround(strikes, atmIdx, strikeCount));

  const maxCallOi = $derived(maxOi(visible, 'ce'));
  const maxPutOi = $derived(maxOi(visible, 'pe'));
  const ceRanks = $derived(volumeRanks(visible, 'ce'));
  const peRanks = $derived(volumeRanks(visible, 'pe'));
  const maxCEVol = $derived(topVolume(visible, 'ce'));
  const maxPEVol = $derived(topVolume(visible, 'pe'));

  const m = $derived(chain ? metrics(chain) : undefined);
  const pcr = $derived(m?.pcr);
  const maxPain = $derived(m?.maxPain);
  const atmIv = $derived.by(() => {
    if (atmIdx < 0) return undefined;
    const s = strikes[atmIdx];
    return s?.ce?.iv ?? s?.pe?.iv;
  });

  const expiries = $derived(chain?.expiries?.slice(0, 8) ?? []);
  const currentExpiry = $derived(selectedExpiry ?? chain?.expiry ?? '');

  // --- live clock ----------------------------------------------------------
  let now = $state(new Date());
  $effect(() => {
    const t = setInterval(() => (now = new Date()), 1000);
    return () => clearInterval(t);
  });
  const clock = $derived(
    new Intl.DateTimeFormat('en-GB', {
      timeZone: 'Asia/Kolkata',
      day: '2-digit',
      month: 'short',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false
    }).format(now)
  );

  // --- small view helpers --------------------------------------------------
  function pctTone(v?: number): 'up' | 'down' | 'flat' {
    if (v == null || Number.isNaN(v)) return 'flat';
    return v > 0 ? 'up' : v < 0 ? 'down' : 'flat';
  }
  function ltpText(leg?: Leg): string {
    return leg?.ltp != null ? formatPrice(leg.ltp) : '—';
  }
  function ivText(leg?: Leg, fallback?: Leg): string {
    const iv = leg?.iv ?? fallback?.iv;
    return iv != null ? iv.toFixed(1) : '—';
  }

  // Close the expiry menu after a pick.
  let expiryMenu = $state<HTMLDetailsElement>();
  function pickExpiry(exp: string) {
    selectedExpiry = exp;
    if (expiryMenu) expiryMenu.open = false;
  }
</script>

<div class="chain-page">
  <!-- 1. Control bar ------------------------------------------------------ -->
  <section class="panel controls">
    <div class="row">
      <!-- instrument pill -->
      <div class="instrument">
        <button
          type="button"
          class="cycle"
          aria-label="Previous instrument"
          onclick={() => cycle(-1)}
        >
          ‹
        </button>
        <span class="inst-body">
          <span class="badge">{instrument.badge}</span>
          <span class="inst-name">{instrument.short}</span>
        </span>
        <button type="button" class="cycle" aria-label="Next instrument" onclick={() => cycle(1)}>
          ›
        </button>
      </div>

      <!-- expiry dropdown -->
      <details class="expiry" bind:this={expiryMenu}>
        <summary aria-label="Select expiry">
          {#if currentExpiry}
            {expiryLabel(currentExpiry)}
            <span class="days">({daysAwayLabel(currentExpiry)})</span>
          {:else}
            Expiry
          {/if}
          <span class="caret" aria-hidden="true"><IconChevronDown /></span>
        </summary>
        <div class="expiry-menu">
          {#each expiries as exp (exp)}
            <button
              type="button"
              class="expiry-item"
              class:selected={exp === currentExpiry}
              onclick={() => pickExpiry(exp)}
            >
              <span>{expiryLabel(exp)}</span>
              <span class="days">{daysAwayLabel(exp)}</span>
            </button>
          {/each}
          {#if expiries.length === 0}
            <p class="expiry-empty">No expiries</p>
          {/if}
        </div>
      </details>

      <!-- spot / future / vix -->
      <div class="stats">
        <span class="stat">
          <span class="stat-label">Spot</span>
          <span class="stat-value mc-numeric">{spot != null ? formatPrice(spot) : '—'}</span>
          {#if spotChange != null}
            <span class="stat-chg {pctTone(spotChange)}">{signedPct(spotChange, 2)}</span>
          {/if}
        </span>
        <span class="stat">
          <span class="stat-label">Future</span>
          <span class="stat-value mc-numeric">{future != null ? formatPrice(future) : '—'}</span>
        </span>
        <span class="stat">
          <span class="stat-label">VIX</span>
          <span class="stat-value mc-numeric">—</span>
        </span>
      </div>

      <!-- live clock -->
      <div class="clock">
        <span class="clock-ico" aria-hidden="true"><IconClock /></span>
        <span class="mc-numeric">{clock} IST</span>
        <span class="dot" class:pulse={refreshing} aria-hidden="true"></span>
      </div>
    </div>

    <div class="row row2">
      <span class="strikes-label">Strikes ±ATM:</span>
      {#each STRIKE_COUNTS as c (c)}
        <button
          type="button"
          class="toggle"
          class:active={strikeCount === c}
          onclick={() => (strikeCount = c)}
        >
          {c === 'All' ? 'All' : `±${c}`}
        </button>
      {/each}

      <div class="summary">
        <span class="sum-chip">
          <span class="sum-label">PCR</span>
          <span class="sum-value {pcr != null && pcr >= 1 ? 'up' : 'down'}">
            {pcr != null ? pcr.toFixed(2) : '—'}
          </span>
        </span>
        <span class="sum-chip">
          <span class="sum-label">Max Pain</span>
          <span class="sum-value amber">
            {maxPain != null && Number.isFinite(maxPain) ? formatInt(maxPain) : '—'}
          </span>
        </span>
        <span class="sum-chip">
          <span class="sum-label">ATM IV</span>
          <span class="sum-value neutral">{atmIv != null ? `${atmIv.toFixed(1)}%` : '—'}</span>
        </span>
      </div>
    </div>
  </section>

  <!-- 2. Chain table ------------------------------------------------------ -->
  <section class="panel table-panel">
    <div class="scroll">
      <table>
        <thead>
          <tr class="head-a">
            <th class="call-head" colspan="5">Call</th>
            <th class="center-head" colspan="2"></th>
            <th class="put-head" colspan="5">Put</th>
          </tr>
          <tr class="head-b">
            <th class="ce l">Buildup</th>
            <th class="ce">Volume</th>
            <th class="ce">OI Chg%</th>
            <th class="ce">OI</th>
            <th class="ce">LTP</th>
            <th class="center bl">Strike ↑</th>
            <th class="center br">IV</th>
            <th class="pe">LTP</th>
            <th class="pe">OI</th>
            <th class="pe">OI Chg%</th>
            <th class="pe">Volume</th>
            <th class="pe">Buildup</th>
          </tr>
        </thead>
        <tbody>
          {#if loading}
            {#each Array(16) as _, i (i)}
              <tr class="skeleton-row">
                <td colspan="12"><span class="skeleton"></span></td>
              </tr>
            {/each}
          {:else}
            {#each visible as s (s.strike)}
              {@const isAtm = s.strike === atmStrike}
              {@const isMaxPain = maxPain != null && s.strike === maxPain}
              {@const ceChg = oiChangePct(s.ce)}
              {@const peChg = oiChangePct(s.pe)}
              <tr class:atm={isAtm}>
                <!-- CE -->
                <td class="ce l"><BuildupBadge buildup={s.ce?.buildup} /></td>
                <VolCell
                  value={s.ce?.volume}
                  rank={ceRanks.get(s.strike)}
                  top={maxCEVol}
                  side="ce"
                />
                <td class="ce num {pctTone(ceChg)}">{signedPct(ceChg, 0)}</td>
                <td class="ce num oi">
                  <span class="oi-val mc-numeric">{compactIndian(s.ce?.oi)}</span>
                  <OIBar value={s.ce?.oi} max={maxCallOi} side="ce" />
                </td>
                <td class="ce num ltp call-ltp brc">{ltpText(s.ce)}</td>

                <!-- center -->
                <td class="center strike bl">
                  <span class="mc-numeric strike-val">{formatInt(s.strike)}</span>
                  {#if isMaxPain}
                    <span class="tag maxpain">Max Pain</span>
                  {:else if isAtm}
                    <span class="tag atm-tag">ATM</span>
                  {/if}
                </td>
                <td class="center iv br">{ivText(s.ce, s.pe)}</td>

                <!-- PE -->
                <td class="pe num ltp put-ltp">{ltpText(s.pe)}</td>
                <td class="pe num oi">
                  <span class="oi-val mc-numeric">{compactIndian(s.pe?.oi)}</span>
                  <OIBar value={s.pe?.oi} max={maxPutOi} side="pe" />
                </td>
                <td class="pe num {pctTone(peChg)}">{signedPct(peChg, 0)}</td>
                <VolCell
                  value={s.pe?.volume}
                  rank={peRanks.get(s.strike)}
                  top={maxPEVol}
                  side="pe"
                />
                <td class="pe"><BuildupBadge buildup={s.pe?.buildup} /></td>
              </tr>
            {/each}
          {/if}
        </tbody>
      </table>

      {#if !loading && visible.length === 0}
        <div class="empty">
          <span class="empty-ico" aria-hidden="true"><IconChart /></span>
          <p class="empty-title">No option chain data</p>
          <p class="empty-hint">Pick another instrument or expiry, or wait for the next refresh.</p>
        </div>
      {/if}
    </div>
  </section>

  <!-- 3. Legend ----------------------------------------------------------- -->
  <section class="panel legend">
    <span class="leg-item"><BuildupBadge buildup="Short Covering" /> Short Covering</span>
    <span class="leg-item"><BuildupBadge buildup="Long Build-up" /> Long Build-up</span>
    <span class="leg-item"><BuildupBadge buildup="Short Build-up" /> Short Build-up</span>
    <span class="leg-item"><BuildupBadge buildup="Long Unwinding" /> Long Unwinding</span>
    <span class="leg-item"><span class="dot green"></span> Call OI bar</span>
    <span class="leg-item"><span class="dot rose"></span> Put OI bar</span>
    <span class="leg-item"><span class="vol-chip">Vol</span> Top-3 volume — hover for rank</span>
    <span class="leg-note">Refreshes every 15 s · OI lags exchange by 1–3 min</span>
  </section>
</div>

<style>
  .chain-page {
    display: flex;
    flex-direction: column;
    gap: var(--mc-space-3);
    padding: var(--mc-space-4) var(--mc-space-6);
  }

  .panel {
    border: 1px solid var(--mc-border);
    border-radius: var(--mc-radius-lg);
    background: var(--mc-surface);
    box-shadow: var(--mc-shadow);
  }

  /* --- control bar ------------------------------------------------------ */
  .controls {
    padding: var(--mc-space-3) var(--mc-space-4);
  }

  .row {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--mc-space-3);
  }

  .row2 {
    margin-top: 0.625rem;
    border-top: 1px solid var(--mc-border);
    padding-top: 0.625rem;
    gap: var(--mc-space-2);
  }

  .instrument {
    display: inline-flex;
    align-items: center;
    gap: var(--mc-space-2);
    border: 1px solid var(--mc-border);
    border-radius: var(--mc-radius);
    background: var(--mc-surface-raised);
    padding: 0.25rem 0.375rem;
  }

  .cycle {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 1.25rem;
    height: 1.25rem;
    border: none;
    border-radius: var(--mc-radius-sm);
    background: transparent;
    color: var(--mc-text-muted);
    font-size: 1rem;
    line-height: 1;
    cursor: pointer;
  }

  .cycle:hover {
    background: var(--mc-surface);
    color: var(--mc-text);
  }

  .inst-body {
    display: inline-flex;
    align-items: center;
    gap: 0.375rem;
  }

  .badge {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    height: 1.5rem;
    min-width: 1.5rem;
    padding: 0 0.25rem;
    border-radius: 999px;
    background: var(--mc-accent);
    color: #fff;
    font-size: var(--mc-text-xs);
    font-weight: 700;
  }

  .inst-name {
    font-weight: 600;
    font-size: var(--mc-text-sm);
  }

  .expiry {
    position: relative;
  }

  .expiry summary {
    display: inline-flex;
    align-items: center;
    gap: 0.375rem;
    height: var(--mc-control-h-sm);
    padding: 0 0.625rem;
    border: 1px solid var(--mc-border);
    border-radius: var(--mc-radius);
    background: var(--mc-surface-raised);
    font-size: var(--mc-text-sm);
    font-weight: 600;
    cursor: pointer;
    list-style: none;
  }

  .expiry summary::-webkit-details-marker {
    display: none;
  }

  .expiry .days {
    color: var(--mc-text-subtle);
    font-weight: 400;
  }

  .caret {
    display: inline-flex;
    opacity: 0.7;
  }

  .caret :global(svg) {
    width: 0.875rem;
    height: 0.875rem;
  }

  .expiry-menu {
    position: absolute;
    left: 0;
    top: calc(100% + 0.375rem);
    z-index: var(--mc-z-dropdown);
    display: flex;
    flex-direction: column;
    min-width: 11rem;
    padding: var(--mc-space-2);
    border: 1px solid var(--mc-border);
    border-radius: var(--mc-radius);
    background: var(--mc-surface);
    box-shadow: var(--mc-shadow);
  }

  .expiry-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--mc-space-4);
    padding: 0.375rem 0.5rem;
    border: none;
    border-radius: var(--mc-radius-sm);
    background: transparent;
    color: var(--mc-text);
    font-size: var(--mc-text-sm);
    text-align: left;
    cursor: pointer;
  }

  .expiry-item:hover {
    background: var(--mc-surface-raised);
  }

  .expiry-item.selected {
    background: var(--mc-accent-weak);
    color: var(--mc-accent);
  }

  .expiry-item .days {
    color: var(--mc-text-subtle);
  }

  .expiry-empty {
    margin: 0;
    padding: 0.375rem 0.5rem;
    color: var(--mc-text-subtle);
    font-size: var(--mc-text-sm);
  }

  .stats {
    display: inline-flex;
    align-items: center;
    gap: var(--mc-space-4);
    font-size: var(--mc-text-sm);
  }

  .stat {
    display: inline-flex;
    align-items: baseline;
    gap: 0.375rem;
  }

  .stat-label {
    color: var(--mc-text-subtle);
  }

  .stat-value {
    font-weight: 700;
    color: var(--mc-text);
  }

  .stat-chg.up,
  .sum-value.up {
    color: var(--mc-bullish);
  }

  .stat-chg.down,
  .sum-value.down {
    color: var(--mc-bearish);
  }

  .stat-chg.flat {
    color: var(--mc-text-subtle);
  }

  .clock {
    margin-left: auto;
    display: inline-flex;
    align-items: center;
    gap: 0.375rem;
    color: var(--mc-text-muted);
    font-size: var(--mc-text-sm);
  }

  .clock-ico {
    display: inline-flex;
  }

  .clock-ico :global(svg) {
    width: 0.9375rem;
    height: 0.9375rem;
  }

  .dot {
    width: 0.5rem;
    height: 0.5rem;
    border-radius: 50%;
    background: var(--mc-bullish);
  }

  .dot.pulse {
    animation: pulse 1.2s ease-in-out infinite;
  }

  @keyframes pulse {
    0%,
    100% {
      opacity: 1;
    }
    50% {
      opacity: 0.35;
    }
  }

  /* --- strike toggles + summary chips ----------------------------------- */
  .strikes-label {
    color: var(--mc-text-muted);
    font-size: var(--mc-text-sm);
    margin-right: 0.25rem;
  }

  .toggle {
    border: 1px solid var(--mc-border);
    border-radius: var(--mc-radius-sm);
    background: transparent;
    color: var(--mc-text-muted);
    padding: 0.125rem 0.5rem;
    font-size: var(--mc-text-xs);
    font-weight: 600;
    cursor: pointer;
  }

  .toggle:hover {
    border-color: var(--mc-border-strong);
    color: var(--mc-text);
  }

  .toggle.active {
    border-color: color-mix(in srgb, var(--mc-accent) 45%, transparent);
    background: var(--mc-accent-weak);
    color: var(--mc-accent);
  }

  .summary {
    margin-left: auto;
    display: inline-flex;
    gap: var(--mc-space-3);
  }

  .sum-chip {
    display: inline-flex;
    align-items: center;
    gap: 0.375rem;
    border: 1px solid var(--mc-border);
    border-radius: 999px;
    background: var(--mc-surface-raised);
    padding: 0.1875rem 0.625rem;
    font-size: var(--mc-text-xs);
  }

  .sum-label {
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--mc-text-subtle);
  }

  .sum-value {
    font-weight: 700;
  }

  .sum-value.amber {
    color: var(--mc-warning);
  }

  .sum-value.neutral {
    color: var(--mc-text);
  }

  /* --- table ------------------------------------------------------------ */
  .table-panel {
    padding: 0;
    overflow: hidden;
  }

  .scroll {
    overflow-x: auto;
  }

  table {
    width: 100%;
    min-width: 1100px;
    border-collapse: collapse;
    font-size: var(--mc-text-sm);
  }

  th {
    padding: var(--mc-space-2) var(--mc-space-3);
    font-weight: 600;
    white-space: nowrap;
  }

  .head-a th {
    text-align: center;
    font-size: var(--mc-text-xs);
    font-weight: 700;
    letter-spacing: 0.12em;
    text-transform: uppercase;
  }

  .call-head {
    background: color-mix(in srgb, var(--mc-bullish) 12%, transparent);
    color: var(--mc-bullish);
  }

  .put-head {
    background: color-mix(in srgb, var(--mc-bearish) 12%, transparent);
    color: var(--mc-bearish);
  }

  .center-head {
    background: var(--mc-surface-raised);
    border-left: 1px solid var(--mc-border);
    border-right: 1px solid var(--mc-border);
  }

  .head-b th {
    font-size: var(--mc-text-xs);
    font-weight: 600;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    border-bottom: 1px solid var(--mc-border);
  }

  .head-b th.ce {
    background: color-mix(in srgb, var(--mc-bullish) 12%, transparent);
    color: var(--mc-bullish);
    text-align: right;
  }

  .head-b th.ce.l {
    text-align: left;
  }

  .head-b th.pe {
    background: color-mix(in srgb, var(--mc-bearish) 12%, transparent);
    color: var(--mc-bearish);
    text-align: left;
  }

  .head-b th.center {
    background: var(--mc-surface-raised);
    color: var(--mc-text-muted);
    text-align: center;
  }

  th.bl,
  td.bl {
    border-left: 1px solid var(--mc-border);
  }

  th.br,
  td.br {
    border-right: 1px solid var(--mc-border);
  }

  tbody td {
    padding: var(--mc-space-2) var(--mc-space-3);
    border-bottom: 1px solid var(--mc-border);
    white-space: nowrap;
  }

  tbody tr:last-child td {
    border-bottom: none;
  }

  tbody tr:hover td {
    background: color-mix(in srgb, var(--mc-surface-raised) 55%, transparent);
  }

  tr.atm td {
    background: color-mix(in srgb, var(--mc-warning) 10%, transparent);
  }

  tr.atm:hover td {
    background: color-mix(in srgb, var(--mc-warning) 16%, transparent);
  }

  td.num {
    text-align: right;
    font-family: var(--mc-font-mono);
    font-variant-numeric: tabular-nums;
  }

  td.pe.num {
    text-align: left;
  }

  td.up {
    color: var(--mc-bullish);
  }

  td.down {
    color: var(--mc-bearish);
  }

  td.flat {
    color: var(--mc-text-subtle);
  }

  .ltp {
    font-weight: 600;
  }

  .call-ltp {
    color: var(--mc-bullish);
  }

  .put-ltp {
    color: var(--mc-bearish);
  }

  .brc {
    border-right: 1px solid var(--mc-border);
  }

  .oi {
    line-height: 1.2;
  }

  td.ce.oi {
    text-align: right;
  }

  td.pe.oi {
    text-align: left;
  }

  .oi-val {
    display: block;
    margin-bottom: 0.1875rem;
  }

  td.ce.oi :global(.track) {
    margin-left: auto;
  }

  td.pe.oi :global(.track) {
    margin-right: auto;
  }

  .center {
    text-align: center;
    background: color-mix(in srgb, var(--mc-surface-raised) 45%, transparent);
  }

  .strike {
    font-weight: 700;
  }

  .strike-val {
    font-size: var(--mc-text-base);
  }

  .iv {
    color: var(--mc-text-muted);
  }

  .tag {
    display: inline-block;
    margin-left: 0.375rem;
    padding: 0.0625rem 0.25rem;
    border-radius: var(--mc-radius-sm);
    font-size: 0.5625rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.03em;
    vertical-align: middle;
  }

  .tag.maxpain {
    background: color-mix(in srgb, var(--mc-warning) 22%, transparent);
    color: var(--mc-warning);
  }

  .tag.atm-tag {
    background: var(--mc-border-strong);
    color: var(--mc-text-muted);
  }

  /* --- loading / empty -------------------------------------------------- */
  .skeleton-row td {
    padding: var(--mc-space-2) var(--mc-space-3);
  }

  .skeleton {
    display: block;
    height: 2.25rem;
    width: 100%;
    border-radius: var(--mc-radius);
    background: linear-gradient(
      90deg,
      var(--mc-surface-raised) 25%,
      color-mix(in srgb, var(--mc-surface-raised) 60%, var(--mc-border)) 37%,
      var(--mc-surface-raised) 63%
    );
    background-size: 400% 100%;
    animation: shimmer 1.4s ease infinite;
  }

  @keyframes shimmer {
    0% {
      background-position: 100% 0;
    }
    100% {
      background-position: 0 0;
    }
  }

  .empty {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: var(--mc-space-2);
    padding: var(--mc-space-8) var(--mc-space-4);
    text-align: center;
  }

  .empty-ico {
    display: inline-flex;
    color: var(--mc-text-subtle);
  }

  .empty-ico :global(svg) {
    width: 2rem;
    height: 2rem;
  }

  .empty-title {
    margin: 0;
    font-weight: 600;
    color: var(--mc-text);
  }

  .empty-hint {
    margin: 0;
    font-size: var(--mc-text-sm);
    color: var(--mc-text-subtle);
  }

  /* --- legend ----------------------------------------------------------- */
  .legend {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--mc-space-6);
    padding: var(--mc-space-4);
    font-size: var(--mc-text-xs);
    color: var(--mc-text-muted);
  }

  .leg-item {
    display: inline-flex;
    align-items: center;
    gap: 0.375rem;
  }

  .legend .dot.green {
    background: var(--mc-bullish);
  }

  .legend .dot.rose {
    background: var(--mc-bearish);
  }

  .vol-chip {
    padding: 0.0625rem 0.25rem;
    border-radius: var(--mc-radius-sm);
    background: color-mix(in srgb, var(--mc-bullish) 20%, transparent);
    color: var(--mc-bullish);
    font-weight: 600;
  }

  .leg-note {
    margin-left: auto;
    color: var(--mc-text-subtle);
  }

  @media (max-width: 40rem) {
    .chain-page {
      padding: var(--mc-space-3) var(--mc-space-3);
    }

    .clock {
      margin-left: 0;
    }
  }
</style>
