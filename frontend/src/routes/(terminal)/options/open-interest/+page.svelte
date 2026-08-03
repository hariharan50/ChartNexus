<script lang="ts">
  import { createQuery } from '@tanstack/svelte-query';
  import { toStore } from 'svelte/store';
  import { theme } from '$shared/ui/theme.svelte';
  import IconChart from '$shared/ui/icons/IconChart.svelte';
  import IconChevronDown from '$shared/ui/icons/IconChevronDown.svelte';
  import {
    getOpenInterest,
    inferStep,
    withinWindow,
    deriveBars,
    windowTotals,
    baselineIndex,
    timeLabel,
    fmtOi,
    fmtSigned,
    OI_INSTRUMENTS,
    type OiView,
    type OiMode
  } from './oi-data';
  import OpenInterestChart from './components/OpenInterestChart.svelte';
  import SentimentDonut from './components/SentimentDonut.svelte';
  import PcrDonut from './components/PcrDonut.svelte';
  import BarPair from './components/BarPair.svelte';

  const MODES: { key: OiMode; label: string }[] = [
    { key: 'change_total', label: 'OI Change+Total' },
    { key: 'change', label: 'OI Change' },
    { key: 'total', label: 'Total OI' }
  ];
  const STRIKE_FILTERS: { label: string; value: 'all' | number }[] = [
    { label: 'All', value: 'all' },
    { label: 'ATM', value: 2 },
    { label: '5', value: 5 },
    { label: '10', value: 10 },
    { label: '20', value: 20 }
  ];
  const QUICK_RANGES: { label: string; value: number | 'all' }[] = [
    { label: 'Last 3 min', value: 3 },
    { label: 'Last 5 min', value: 5 },
    { label: 'Last 10 min', value: 10 },
    { label: 'Last 15 min', value: 15 },
    { label: 'Last 30 min', value: 30 },
    { label: 'Last 1 hr', value: 60 },
    { label: 'Last 2 hr', value: 120 },
    { label: 'Last 3 hr', value: 180 },
    { label: 'All', value: 'all' }
  ];

  let instIdx = $state(0);
  let mode = $state<OiMode>('change_total');
  let showLot = $state(false);
  let strikeFilter = $state<'all' | number>(10);
  let quickRange = $state<number | 'all'>('all');
  /** Slider position, or -1 to follow live (far right). */
  let frameIdx = $state(-1);

  const instrument = $derived(OI_INSTRUMENTS[instIdx] ?? OI_INSTRUMENTS[0]!);
  const isDark = $derived(theme.value === 'dark');

  function cycle(delta: number) {
    instIdx = (instIdx + delta + OI_INSTRUMENTS.length) % OI_INSTRUMENTS.length;
    frameIdx = -1;
    quickRange = 'all';
  }

  const query = createQuery<OiView>(
    toStore(() => ({
      queryKey: ['options-lab', 'oi', instrument.symbol],
      queryFn: () => getOpenInterest(instrument.symbol),
      refetchInterval: 15_000
    }))
  );

  const view = $derived($query.data);
  const lotSize = $derived(view?.lot_size ?? 75);

  // -- client re-derivation -------------------------------------------------
  const strikes = $derived(view ? view.strikes.map((r) => r.strike) : []);
  const step = $derived(inferStep(strikes));
  const visible = $derived(
    view
      ? withinWindow(strikes, view.atm_strike, step, strikeFilter === 'all' ? 0 : strikeFilter)
      : []
  );

  const series = $derived(view?.series ?? []);
  const hasSeries = $derived(series.length >= 2);
  const lastIdx = $derived(Math.max(0, series.length - 1));
  const nowIdx = $derived(frameIdx < 0 ? lastIdx : Math.min(frameIdx, lastIdx));
  const openIdx = $derived(hasSeries ? baselineIndex(series, nowIdx, quickRange) : 0);

  const nowFrame = $derived(hasSeries ? series[nowIdx] : undefined);
  const openFrame = $derived(hasSeries ? series[openIdx] : undefined);

  const bars = $derived(view ? deriveBars(view, visible, openFrame, nowFrame) : []);
  const totals = $derived(view ? windowTotals(view, openFrame, nowFrame) : undefined);

  const openLabel = $derived(
    nowFrame && openFrame ? timeLabel(openFrame.t) : view ? timeLabel(view.open_ts) : '—'
  );
  const nowLabel = $derived(nowFrame ? timeLabel(nowFrame.t) : view ? timeLabel(view.now_ts) : '—');

  const expiryLabel = $derived.by(() => {
    if (!view?.expiry_date) return 'Nearest expiry';
    const d = new Date(view.expiry_date);
    const days = Math.max(0, Math.round((d.getTime() - Date.now()) / 86_400_000));
    const label = new Intl.DateTimeFormat('en-GB', {
      day: '2-digit',
      month: 'short',
      year: 'numeric'
    }).format(d);
    return `${label} (${days === 0 ? 'today' : `${days}d`})`;
  });

  function resetSlider() {
    frameIdx = -1;
    quickRange = 'all';
  }

  // -- live clock -----------------------------------------------------------
  let now = $state(new Date());
  $effect(() => {
    const t = setInterval(() => (now = new Date()), 1000);
    return () => clearInterval(t);
  });
  const clock = $derived(
    new Intl.DateTimeFormat('en-GB', {
      timeZone: 'Asia/Kolkata',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false
    }).format(now)
  );
</script>

<svelte:head>
  <title>Open Interest · Options Lab</title>
</svelte:head>

<div class="page">
  {#if $query.isError}
    <div class="banner" role="alert">
      <span>Couldn’t load open interest.</span>
      <button type="button" onclick={() => $query.refetch()}>Retry</button>
    </div>
  {:else if !view && $query.isPending}
    <div class="panel muted">Loading Open Interest…</div>
  {:else if view && view.data_quality === 'empty'}
    <div class="panel muted">No option-chain data available yet.</div>
  {:else if view && totals}
    <div class="layout">
      <!-- LEFT SIDEBAR -->
      <aside class="sidebar">
        <section class="panel">
          <h2 class="p-title">Settings</h2>

          <div class="instrument">
            <span class="badge">{instrument.badge}</span>
            <span class="short">{instrument.short}</span>
            <span class="cyclers">
              <button type="button" aria-label="Previous" onclick={() => cycle(-1)}>‹</button>
              <button type="button" aria-label="Next" onclick={() => cycle(1)}>›</button>
            </span>
          </div>

          <p class="sub-label">Select Mode</p>
          <div class="mode-grid">
            <button type="button" class="seg active">Live</button>
            <button type="button" class="seg" disabled title="Historical mode coming soon">
              Historical
            </button>
          </div>

          <p class="sub-label">Expiry</p>
          <div class="select">
            <span>{expiryLabel}</span>
            <span class="caret" aria-hidden="true"><IconChevronDown /></span>
          </div>
          <p class="hint">Live chain is served for the nearest expiry.</p>

          <p class="sub-label">Strikes above-below ATM</p>
          <div class="filter-row">
            {#each STRIKE_FILTERS as f (f.label)}
              <button
                type="button"
                class="chip"
                class:active={strikeFilter === f.value}
                onclick={() => (strikeFilter = f.value)}
              >
                {f.label}
              </button>
            {/each}
          </div>
        </section>

        <section class="panel">
          <h2 class="p-title">
            <span class="ico"><IconChart /></span> Market Sentiment
            <span class="dim">(based on OI)</span>
          </h2>
          <SentimentDonut label={view.sentiment.label} percent={view.sentiment.bullish_pct} />

          <div class="pcr-line">
            PCR: <strong>{totals.pcr.toFixed(2)}</strong>
            <span class:up={totals.pcrChange >= 0} class:down={totals.pcrChange < 0}>
              ({totals.pcrChange >= 0 ? '+' : ''}{totals.pcrChange.toFixed(2)})
            </span>
          </div>

          <div class="insight-box">
            <p class="ib-title">ⓘ Market Insight</p>
            <p class="ib-body">{view.sentiment.insight}</p>
          </div>
          <div class="analysis-box">
            <p class="ab-title">ⓘ Analysis</p>
            <p class="ab-body">{view.sentiment.analysis}</p>
          </div>
        </section>
      </aside>

      <!-- RIGHT MAIN -->
      <div class="main">
        <section class="panel chart-panel">
          <div class="chart-top">
            <div class="mode-tabs">
              {#each MODES as m (m.key)}
                <button
                  type="button"
                  class="pill"
                  class:active={mode === m.key}
                  onclick={() => (mode = m.key)}
                >
                  {m.label}
                </button>
              {/each}
            </div>
            <div class="chart-top-right">
              <label class="show-lot">
                <span>Show Lot</span>
                <input type="checkbox" bind:checked={showLot} />
                <span class="switch" class:on={showLot}><span class="knob"></span></span>
              </label>
              <span class="live">
                <span class="dot" class:pulse={$query.isFetching}></span>
                Live — {clock} IST
              </span>
            </div>
          </div>

          <OpenInterestChart
            {bars}
            {mode}
            spot={view.spot}
            maxPain={view.max_pain}
            {showLot}
            {lotSize}
            {isDark}
            showTooltip={true}
            {openLabel}
            {nowLabel}
          />

          <div class="legend">
            <span><i class="sw call solid"></i> Call OI</span>
            <span><i class="sw call outline"></i> Call OI Decrease</span>
            <span><i class="sw call hatch"></i> Call OI Increase</span>
            <span><i class="sw put solid"></i> Put OI</span>
            <span><i class="sw put outline"></i> Put OI Decrease</span>
            <span><i class="sw put hatch"></i> Put OI Increase</span>
          </div>

          <!-- time slider -->
          <div class="slider-row">
            {#if hasSeries}
              <button type="button" class="reset" onclick={resetSlider}>Reset</button>
            {/if}
            <span class="end">{openLabel}</span>
            <input
              class="scrub"
              type="range"
              min="0"
              max={lastIdx}
              value={nowIdx}
              disabled={!hasSeries}
              oninput={(e) => {
                const v = Number(e.currentTarget.value);
                frameIdx = v >= lastIdx ? -1 : v;
              }}
            />
            <span class="end">{nowLabel}</span>
          </div>

          <div class="quick">
            {#each QUICK_RANGES as q (q.label)}
              <button
                type="button"
                class="pill sm"
                class:active={quickRange === q.value}
                disabled={!hasSeries}
                onclick={() => (quickRange = q.value)}
              >
                {q.label}
              </button>
            {/each}
          </div>

          <p class="caption">
            Showing OI build-up from {openLabel} to {nowLabel}. Drag the slider to scrub through the
            session.{view.data_quality === 'live_proxy'
              ? ' (open estimated from day-over-day OI change)'
              : ''}
          </p>
        </section>

        <div class="summary">
          <section class="panel sc">
            <h3><span class="ico"><IconChart /></span> Open Interest Change</h3>
            <BarPair
              callValue={totals.callChg}
              putValue={totals.putChg}
              callLabel={fmtSigned(totals.callChg, showLot, lotSize)}
              putLabel={fmtSigned(totals.putChg, showLot, lotSize)}
            />
          </section>
          <section class="panel sc">
            <h3><span class="ico"><IconChart /></span> Total Open Interest</h3>
            <BarPair
              callValue={totals.callNow}
              putValue={totals.putNow}
              callLabel={fmtOi(totals.callNow, showLot, lotSize)}
              putLabel={fmtOi(totals.putNow, showLot, lotSize)}
            />
          </section>
          <section class="panel sc">
            <h3><span class="ico"><IconChart /></span> Put/Call Ratio</h3>
            <PcrDonut pcr={totals.pcr} callNow={totals.callNow} putNow={totals.putNow} />
          </section>
        </div>
      </div>
    </div>
  {/if}
</div>

<style>
  .page {
    max-width: 96rem;
    margin: 0 auto;
    padding: var(--mc-space-6);
  }

  .layout {
    display: grid;
    grid-template-columns: 290px 1fr;
    gap: var(--mc-space-5, 1.25rem);
    align-items: start;
  }

  .sidebar,
  .main {
    display: flex;
    flex-direction: column;
    gap: var(--mc-space-5, 1.25rem);
    min-width: 0;
  }

  .panel {
    border: 1px solid var(--mc-border);
    border-radius: var(--mc-radius-lg);
    background: var(--mc-surface);
    box-shadow: var(--mc-shadow);
    padding: var(--mc-space-4);
  }

  .panel.muted {
    color: var(--mc-text-muted);
    text-align: center;
  }

  .banner {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--mc-space-3);
    padding: var(--mc-space-4);
    border: 1px solid var(--mc-bearish);
    border-radius: var(--mc-radius-lg);
    color: var(--mc-text);
  }

  .banner button {
    padding: 0.375rem 0.75rem;
    border: 1px solid var(--mc-border-strong);
    border-radius: var(--mc-radius);
    background: var(--mc-surface-raised);
    color: var(--mc-text);
    cursor: pointer;
  }

  .p-title {
    display: flex;
    align-items: center;
    gap: 0.375rem;
    margin: 0 0 var(--mc-space-3);
    font-size: var(--mc-text-base);
    font-weight: 700;
  }

  .p-title .dim {
    font-size: var(--mc-text-xs);
    font-weight: 400;
    color: var(--mc-text-subtle);
  }

  .ico {
    display: inline-flex;
    color: var(--mc-text-muted);
  }

  .ico :global(svg) {
    width: 1rem;
    height: 1rem;
  }

  .instrument {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.5rem 0.625rem;
    border: 1px solid var(--mc-border);
    border-radius: var(--mc-radius);
    background: var(--mc-surface-raised);
  }

  .badge {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 1.75rem;
    height: 1.75rem;
    border-radius: 999px;
    background: var(--mc-accent-weak);
    color: var(--mc-accent);
    font-size: var(--mc-text-xs);
    font-weight: 700;
  }

  .short {
    font-weight: 700;
  }

  .cyclers {
    margin-left: auto;
    display: inline-flex;
    gap: 0.25rem;
  }

  .cyclers button {
    width: 1.75rem;
    height: 1.75rem;
    border: 1px solid var(--mc-border);
    border-radius: var(--mc-radius-sm);
    background: var(--mc-surface);
    color: var(--mc-text-muted);
    cursor: pointer;
  }

  .sub-label {
    margin: var(--mc-space-3) 0 0.375rem;
    font-size: var(--mc-text-xs);
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--mc-text-subtle);
  }

  .mode-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.5rem;
  }

  .seg {
    padding: 0.5rem;
    border: 1px solid var(--mc-border);
    border-radius: var(--mc-radius);
    background: transparent;
    color: var(--mc-text-muted);
    font-weight: 600;
    cursor: pointer;
  }

  .seg.active {
    border-color: color-mix(in srgb, var(--mc-accent) 45%, transparent);
    background: var(--mc-accent-weak);
    color: var(--mc-accent);
  }

  .seg:disabled {
    color: var(--mc-text-subtle);
    cursor: not-allowed;
  }

  .select {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.5rem 0.625rem;
    border: 1px solid var(--mc-border);
    border-radius: var(--mc-radius);
    background: var(--mc-surface-raised);
    font-weight: 600;
  }

  .caret :global(svg) {
    width: 0.875rem;
    height: 0.875rem;
    opacity: 0.7;
  }

  .hint {
    margin: 0.375rem 0 0;
    font-size: var(--mc-text-xs);
    color: var(--mc-text-subtle);
  }

  .filter-row {
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 0.25rem;
  }

  .chip {
    padding: 0.375rem 0;
    border: 1px solid var(--mc-border);
    border-radius: var(--mc-radius-sm);
    background: transparent;
    color: var(--mc-text-muted);
    font-size: var(--mc-text-xs);
    font-weight: 600;
    cursor: pointer;
  }

  .chip.active {
    border-color: color-mix(in srgb, var(--mc-accent) 45%, transparent);
    background: var(--mc-accent-weak);
    color: var(--mc-accent);
  }

  .pcr-line {
    margin: var(--mc-space-4) 0 var(--mc-space-3);
    padding-top: var(--mc-space-3);
    border-top: 1px solid var(--mc-border);
    text-align: center;
    font-size: var(--mc-text-sm);
  }

  .pcr-line .up {
    color: var(--mc-bullish);
  }

  .pcr-line .down {
    color: var(--mc-bearish);
  }

  .insight-box,
  .analysis-box {
    margin-top: var(--mc-space-2);
    padding: var(--mc-space-3);
    border-radius: var(--mc-radius);
    font-size: var(--mc-text-sm);
  }

  .insight-box {
    border: 1px solid color-mix(in srgb, var(--mc-accent) 30%, transparent);
    background: var(--mc-accent-weak);
  }

  .ib-title {
    margin: 0 0 0.25rem;
    font-weight: 700;
    color: var(--mc-accent);
  }

  .ib-body {
    margin: 0;
    color: var(--mc-text);
  }

  .analysis-box {
    border: 1px solid var(--mc-border);
    background: var(--mc-surface-raised);
  }

  .ab-title {
    margin: 0 0 0.25rem;
    font-weight: 700;
    color: var(--mc-text-muted);
  }

  .ab-body {
    margin: 0;
    color: var(--mc-text-muted);
  }

  /* -- chart panel -- */
  .chart-top {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--mc-space-3);
    flex-wrap: wrap;
    margin-bottom: var(--mc-space-3);
  }

  .mode-tabs,
  .quick {
    display: inline-flex;
    flex-wrap: wrap;
    gap: 0.375rem;
  }

  .pill {
    padding: 0.4375rem 0.75rem;
    border: 1px solid var(--mc-border);
    border-radius: var(--mc-radius);
    background: transparent;
    color: var(--mc-text-muted);
    font-size: var(--mc-text-sm);
    font-weight: 600;
    cursor: pointer;
  }

  .pill.sm {
    padding: 0.3125rem 0.625rem;
    font-size: var(--mc-text-xs);
  }

  .pill.active {
    border-color: color-mix(in srgb, var(--mc-accent) 45%, transparent);
    background: var(--mc-accent-weak);
    color: var(--mc-accent);
  }

  .pill:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .chart-top-right {
    display: inline-flex;
    align-items: center;
    gap: var(--mc-space-4);
  }

  .show-lot {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    font-size: var(--mc-text-sm);
    color: var(--mc-text-muted);
    cursor: pointer;
  }

  .show-lot input {
    position: absolute;
    opacity: 0;
    width: 0;
    height: 0;
  }

  .switch {
    position: relative;
    width: 2.25rem;
    height: 1.25rem;
    border-radius: 999px;
    background: var(--mc-border-strong);
    transition: background var(--mc-duration-fast);
  }

  .switch.on {
    background: var(--mc-bullish);
  }

  .knob {
    position: absolute;
    top: 2px;
    left: 2px;
    width: 1rem;
    height: 1rem;
    border-radius: 50%;
    background: #fff;
    transition: transform var(--mc-duration-fast);
  }

  .switch.on .knob {
    transform: translateX(1rem);
  }

  .live {
    display: inline-flex;
    align-items: center;
    gap: 0.375rem;
    font-size: var(--mc-text-sm);
    color: var(--mc-text-muted);
    white-space: nowrap;
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
    50% {
      opacity: 0.35;
    }
  }

  .legend {
    display: flex;
    flex-wrap: wrap;
    justify-content: center;
    gap: var(--mc-space-4);
    margin-top: var(--mc-space-2);
    font-size: var(--mc-text-xs);
    color: var(--mc-text-muted);
  }

  .legend span {
    display: inline-flex;
    align-items: center;
    gap: 0.375rem;
  }

  .sw {
    width: 0.75rem;
    height: 0.75rem;
    border-radius: 2px;
  }

  .sw.call {
    --c: #22c55e;
  }

  .sw.put {
    --c: #ef4444;
  }

  .sw.solid {
    background: var(--c);
  }

  .sw.outline {
    border: 1px dashed var(--c);
  }

  .sw.hatch {
    border: 1px solid var(--c);
    background: repeating-linear-gradient(
      -45deg,
      var(--c),
      var(--c) 1px,
      transparent 1px,
      transparent 3px
    );
  }

  .slider-row {
    display: flex;
    align-items: center;
    gap: var(--mc-space-3);
    margin-top: var(--mc-space-4);
  }

  .reset {
    padding: 0.3125rem 0.75rem;
    border: 1px solid color-mix(in srgb, var(--mc-bearish) 40%, transparent);
    border-radius: var(--mc-radius);
    background: color-mix(in srgb, var(--mc-bearish) 12%, transparent);
    color: var(--mc-bearish);
    font-weight: 600;
    cursor: pointer;
  }

  .end {
    font-size: var(--mc-text-xs);
    color: var(--mc-text-subtle);
    white-space: nowrap;
  }

  .scrub {
    flex: 1;
    accent-color: var(--mc-bearish);
  }

  .quick {
    margin-top: var(--mc-space-3);
  }

  .caption {
    margin: var(--mc-space-3) 0 0;
    font-size: var(--mc-text-xs);
    color: var(--mc-text-subtle);
  }

  /* -- summary -- */
  .summary {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: var(--mc-space-5, 1.25rem);
  }

  .sc h3 {
    display: flex;
    align-items: center;
    gap: 0.375rem;
    margin: 0 0 var(--mc-space-4);
    font-size: var(--mc-text-sm);
    font-weight: 700;
  }

  @media (max-width: 72rem) {
    .layout {
      grid-template-columns: 1fr;
    }

    .summary {
      grid-template-columns: 1fr;
    }
  }
</style>
