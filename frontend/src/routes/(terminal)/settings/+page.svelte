<svelte:head>
  <title>My Plans · Settings · MarketCompass</title>
</svelte:head>

<h1>My Plans</h1>

<div class="plan-state">
  <div class="plan-copy">
    <p class="plan-name">Free plan</p>
    <p class="plan-desc">
      Full access to the live terminal — option chain, PCR, max pain and OI build-up.
    </p>
  </div>
  <span class="badge">Current</span>
</div>

<p class="note">
  Billing isn’t live yet. Paid tiers with higher limits and team seats are on the way — you’ll be
  able to upgrade from here when they land.
</p>

<style>
  h1 {
    margin: 0 0 var(--mc-space-5);
    font-size: var(--mc-text-xl);
    font-weight: 700;
    letter-spacing: -0.01em;
  }

  .plan-state {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: var(--mc-space-4);
    padding: var(--mc-space-5);
    border: 1.5px solid var(--mc-accent);
    border-radius: var(--mc-radius-lg);
    background: var(--mc-accent-weak);
  }

  .plan-name {
    margin: 0;
    font-size: var(--mc-text-lg);
    font-weight: 700;
    letter-spacing: -0.01em;
  }

  .plan-desc {
    margin: var(--mc-space-2) 0 0;
    font-size: var(--mc-text-sm);
    line-height: 1.6;
    color: var(--mc-text-muted);
  }

  .badge {
    flex: none;
    padding: 0.1875rem 0.625rem;
    border-radius: 999px;
    background: var(--mc-accent);
    color: #fff;
    font-size: var(--mc-text-xs);
    font-weight: 700;
  }

  .note {
    margin: var(--mc-space-5) 0 0;
    font-size: var(--mc-text-sm);
    line-height: 1.7;
    color: var(--mc-text-muted);
  }
</style>
