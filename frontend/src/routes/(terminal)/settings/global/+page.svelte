<script lang="ts">
  import { theme, THEME_OPTIONS, type Theme } from '$shared/ui/theme.svelte';
  import { preferences, type CallPutScheme } from '$shared/ui/preferences.svelte';

  // Preview swatches per theme (fixed — they show the target theme, not the
  // active one, so they must not read live tokens).
  const PREVIEW: Record<Theme, { bg: string; panel: string; accent: string; bar: string }> = {
    light: { bg: '#f7f8fa', panel: '#ffffff', accent: '#2f6fe4', bar: '#dfe3eb' },
    warm: { bg: '#f4ede1', panel: '#fffdf8', accent: '#c8551f', bar: '#e6dccb' },
    dark: { bg: '#131722', panel: '#1a1f2e', accent: '#4c8dff', bar: '#2b3145' },
    terminal: { bg: '#0c0c0e', panel: '#16161a', accent: '#e2542a', bar: '#2a2a30' }
  };

  const callPut: { id: CallPutScheme; label: string; call: string; put: string }[] = [
    { id: 'classic', label: 'Classic', call: 'bullish', put: 'bearish' },
    { id: 'inverted', label: 'Inverted', call: 'bearish', put: 'bullish' }
  ];
</script>

<svelte:head>
  <title>Global Settings · Settings · MarketCompass</title>
</svelte:head>

<h1>Global Settings</h1>

<!-- Chart -->
<section class="group first">
  <p class="group-title">Chart</p>
  <div class="toggle-row">
    <div class="toggle-copy">
      <p class="label">Show chart tooltip</p>
      <p class="hint">Reveal price &amp; OI details on chart hover</p>
    </div>
    <button
      type="button"
      role="switch"
      aria-checked={preferences.showChartTooltip}
      aria-label="Show chart tooltip"
      class="switch"
      class:on={preferences.showChartTooltip}
      onclick={() => preferences.setShowChartTooltip(!preferences.showChartTooltip)}
    >
      <span class="knob"></span>
    </button>
  </div>
</section>

<!-- Call / Put colour -->
<section class="group">
  <p class="group-title">Call / Put Colour</p>
  <div class="cards two">
    {#each callPut as scheme (scheme.id)}
      <button
        type="button"
        class="choice"
        class:active={preferences.callPutScheme === scheme.id}
        aria-pressed={preferences.callPutScheme === scheme.id}
        onclick={() => preferences.setCallPutScheme(scheme.id)}
      >
        <span class="choice-head">
          <span class="choice-label">{scheme.label}</span>
          {#if preferences.callPutScheme === scheme.id}<span class="tick">✓</span>{/if}
        </span>
        <span class="legend">
          <span class="leg"><span class="dot {scheme.call}"></span>Call</span>
          <span class="leg"><span class="dot {scheme.put}"></span>Put</span>
        </span>
      </button>
    {/each}
  </div>
</section>

<!-- Appearance -->
<section class="group">
  <p class="group-title">Appearance — Theme</p>
  <div class="cards four">
    {#each THEME_OPTIONS as option (option.id)}
      {@const p = PREVIEW[option.id]}
      <button
        type="button"
        class="theme-card"
        class:active={theme.value === option.id}
        aria-pressed={theme.value === option.id}
        onclick={() => theme.set(option.id)}
      >
        <span class="preview" style="background:{p.bg}">
          {#if theme.value === option.id}<span class="active-badge">Active</span>{/if}
          <span class="preview-panel" style="background:{p.panel}">
            <span class="bar accent" style="background:{p.accent}"></span>
            <span class="bar" style="background:{p.bar}"></span>
            <span class="bar short" style="background:{p.bar}"></span>
          </span>
        </span>
        <span class="theme-label">{option.label}</span>
        <span class="theme-hint">{option.hint}</span>
      </button>
    {/each}
  </div>
</section>

<style>
  h1 {
    margin: 0 0 var(--mc-space-4);
    font-size: var(--mc-text-xl);
    font-weight: 700;
    letter-spacing: -0.01em;
  }

  .group {
    margin-top: var(--mc-space-7);
  }

  .group.first {
    margin-top: var(--mc-space-4);
  }

  .group-title {
    margin: 0 0 var(--mc-space-5);
    font-size: var(--mc-text-xs);
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--mc-text-subtle);
  }

  /* Toggle row */
  .toggle-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--mc-space-6);
  }

  .label {
    margin: 0;
    font-size: var(--mc-text-base);
    font-weight: 700;
  }

  .hint {
    margin: var(--mc-space-2) 0 0;
    font-size: var(--mc-text-sm);
    line-height: 1.6;
    color: var(--mc-text-muted);
  }

  .switch {
    position: relative;
    width: 2.75rem;
    height: 1.5rem;
    flex: none;
    padding: 0;
    border: none;
    border-radius: 999px;
    background: var(--mc-border-strong);
    cursor: pointer;
    transition: background var(--mc-duration-fast) ease;
  }

  .switch.on {
    background: var(--mc-accent);
  }

  .knob {
    position: absolute;
    top: 0.1875rem;
    left: 0.1875rem;
    width: 1.125rem;
    height: 1.125rem;
    border-radius: 50%;
    background: #fff;
    transition: transform var(--mc-duration-fast) ease;
  }

  .switch.on .knob {
    transform: translateX(1.25rem);
  }

  /* Choice cards */
  .cards {
    display: grid;
    gap: var(--mc-space-4);
  }

  .cards.two {
    grid-template-columns: repeat(2, 1fr);
  }

  .cards.four {
    grid-template-columns: repeat(4, 1fr);
  }

  .choice {
    display: flex;
    flex-direction: column;
    gap: var(--mc-space-3);
    padding: var(--mc-space-4);
    border: 1.5px solid var(--mc-border);
    border-radius: var(--mc-radius);
    background: var(--mc-surface);
    text-align: left;
    cursor: pointer;
    transition:
      border-color var(--mc-duration-fast) ease,
      background var(--mc-duration-fast) ease;
  }

  .choice:hover {
    border-color: var(--mc-border-strong);
  }

  .choice.active {
    border-color: var(--mc-accent);
    background: var(--mc-accent-weak);
  }

  .choice-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .choice-label {
    font-size: var(--mc-text-base);
    font-weight: 700;
  }

  .tick {
    color: var(--mc-accent);
    font-weight: 700;
  }

  .legend {
    display: flex;
    gap: var(--mc-space-4);
  }

  .leg {
    display: inline-flex;
    align-items: center;
    gap: 0.375rem;
    font-size: var(--mc-text-xs);
    font-weight: 700;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    color: var(--mc-text-muted);
  }

  .dot {
    width: 0.5rem;
    height: 0.5rem;
    border-radius: 50%;
  }

  .dot.bullish {
    background: var(--mc-bullish);
  }

  .dot.bearish {
    background: var(--mc-bearish);
  }

  /* Theme cards */
  .theme-card {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    padding: 0.375rem;
    border: 1.5px solid var(--mc-border);
    border-radius: var(--mc-radius-lg);
    background: var(--mc-surface);
    text-align: left;
    cursor: pointer;
    transition: border-color var(--mc-duration-fast) ease;
  }

  .theme-card:hover {
    border-color: var(--mc-border-strong);
  }

  .theme-card.active {
    border-color: var(--mc-accent);
  }

  .preview {
    position: relative;
    display: flex;
    align-items: center;
    justify-content: center;
    height: 5rem;
    border-radius: var(--mc-radius);
    overflow: hidden;
  }

  .preview-panel {
    display: flex;
    flex-direction: column;
    gap: 0.375rem;
    width: 78%;
    padding: 0.625rem;
    border-radius: var(--mc-radius-sm);
  }

  .bar {
    height: 0.4375rem;
    border-radius: 999px;
  }

  .bar.accent {
    width: 55%;
  }

  .bar.short {
    width: 70%;
  }

  .active-badge {
    position: absolute;
    top: 0.375rem;
    right: 0.375rem;
    padding: 0.125rem 0.4375rem;
    border-radius: 999px;
    background: var(--mc-accent);
    color: #fff;
    font-size: 0.5625rem;
    font-weight: 700;
    letter-spacing: 0.06em;
    text-transform: uppercase;
  }

  .theme-label {
    margin-top: 0.25rem;
    padding: 0 0.25rem;
    font-size: var(--mc-text-base);
    font-weight: 700;
  }

  .theme-hint {
    padding: 0 0.25rem 0.25rem;
    font-size: var(--mc-text-sm);
    color: var(--mc-text-muted);
  }

  @media (max-width: 60rem) {
    .cards.four {
      grid-template-columns: repeat(2, 1fr);
    }
  }

  @media (max-width: 30rem) {
    .cards.two,
    .cards.four {
      grid-template-columns: 1fr;
    }
  }
</style>
