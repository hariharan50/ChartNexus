<script lang="ts">
  import {
    notificationPreferences,
    type NotificationToggleKey,
    type PushTimeout
  } from '$shared/ui/notification-preferences.svelte';

  interface ToggleDef {
    key: keyof NotificationToggleKey;
    title: string;
    hint: string;
  }

  const accountToggles: ToggleDef[] = [
    {
      key: 'priceAlerts',
      title: 'Price alerts',
      hint: 'When an instrument you track crosses a price level you set.'
    },
    {
      key: 'oiAlerts',
      title: 'Open interest & PCR alerts',
      hint: 'When OI build-up, PCR or max-pain shifts sharply on your watchlist.'
    },
    {
      key: 'brokerStatus',
      title: 'Broker connection',
      hint: 'When your FYERS session expires or a reconnect is needed.'
    },
    {
      key: 'marketSchedule',
      title: 'Market schedule',
      hint: 'Pre-open, open and close reminders for NSE trading sessions.'
    }
  ];

  const emailToggles: ToggleDef[] = [
    {
      key: 'productUpdates',
      title: 'Product updates',
      hint: 'New indicators, tools and terminal features as they ship.'
    },
    {
      key: 'weeklyDigest',
      title: 'Weekly digest',
      hint: 'A Monday summary of your watchlist and open positions.'
    }
  ];

  const pushTimeouts: { id: PushTimeout; label: string }[] = [
    { id: '5', label: '5 Minutes' },
    { id: '10', label: '10 Minutes' },
    { id: '30', label: '30 Minutes' },
    { id: '60', label: '1 Hour' },
    { id: 'off', label: 'Off' }
  ];

  let savedVisible = $state(false);
  let hideTimer: ReturnType<typeof setTimeout> | undefined;

  function flashSaved() {
    savedVisible = true;
    clearTimeout(hideTimer);
    hideTimer = setTimeout(() => {
      savedVisible = false;
    }, 1400);
  }

  function toggle(key: keyof NotificationToggleKey) {
    notificationPreferences.set(key, !notificationPreferences.toggles[key]);
    flashSaved();
  }

  function setPushTimeout(event: Event) {
    notificationPreferences.setPushTimeout(
      (event.currentTarget as HTMLSelectElement).value as PushTimeout
    );
    flashSaved();
  }
</script>

<svelte:head>
  <title>Notifications · Settings · MarketCompass</title>
</svelte:head>

<header class="page-header">
  <h1>Notifications</h1>
  <span class="saved" class:visible={savedVisible} role="status">
    <span class="dot" aria-hidden="true"></span>
    Saved
  </span>
</header>

<section class="group">
  <p class="group-title">Account notifications</p>

  {#each accountToggles as row, i (row.key)}
    <div class="row" class:first={i === 0}>
      <div class="copy">
        <p class="label">{row.title}</p>
        <p class="hint">{row.hint}</p>
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={notificationPreferences.toggles[row.key]}
        aria-label={row.title}
        class="switch"
        class:on={notificationPreferences.toggles[row.key]}
        onclick={() => toggle(row.key)}
      >
        <span class="knob"></span>
      </button>
    </div>
  {/each}

  <div class="row select-row">
    <div class="copy">
      <p class="label">Push notification time-out</p>
      <p class="hint">How long an in-app alert stays visible before it dismisses itself.</p>
    </div>
    <select class="select" value={notificationPreferences.pushTimeout} onchange={setPushTimeout}>
      {#each pushTimeouts as opt (opt.id)}
        <option value={opt.id}>{opt.label}</option>
      {/each}
    </select>
  </div>
</section>

<section class="group">
  <p class="group-title">Email notifications</p>

  {#each emailToggles as row, i (row.key)}
    <div class="row" class:first={i === 0}>
      <div class="copy">
        <p class="label">{row.title}</p>
        <p class="hint">{row.hint}</p>
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={notificationPreferences.toggles[row.key]}
        aria-label={row.title}
        class="switch"
        class:on={notificationPreferences.toggles[row.key]}
        onclick={() => toggle(row.key)}
      >
        <span class="knob"></span>
      </button>
    </div>
  {/each}
</section>

<style>
  .page-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--mc-space-3);
    margin-bottom: var(--mc-space-2);
  }

  h1 {
    margin: 0;
    font-size: var(--mc-text-xl);
    font-weight: 700;
    letter-spacing: -0.01em;
  }

  .saved {
    display: inline-flex;
    align-items: center;
    gap: 0.375rem;
    font-size: var(--mc-text-sm);
    font-weight: 600;
    color: var(--mc-live);
    opacity: 0;
    transition: opacity var(--mc-duration) ease;
  }

  .saved.visible {
    opacity: 1;
  }

  .dot {
    width: 0.5rem;
    height: 0.5rem;
    border-radius: 50%;
    background: var(--mc-live);
  }

  .group {
    margin-top: var(--mc-space-7);
  }

  .group-title {
    margin: 0 0 var(--mc-space-2);
    font-size: var(--mc-text-xs);
    font-weight: 700;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--mc-text-subtle);
  }

  .row {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: var(--mc-space-6);
    margin: 0 calc(-1 * var(--mc-space-4));
    padding: var(--mc-space-5) var(--mc-space-4);
    border-top: 1.5px solid var(--mc-border-strong);
    border-radius: var(--mc-radius);
    transition: background var(--mc-duration-fast) ease;
  }

  .row:hover {
    background: var(--mc-surface-raised);
  }

  .row.first {
    border-top: none;
  }

  .copy {
    min-width: 0;
    max-width: 32rem;
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

  .select-row {
    align-items: center;
  }

  .select {
    flex: none;
    padding: 0.5rem 0.75rem;
    border: 1px solid var(--mc-border-strong);
    border-radius: var(--mc-radius);
    background: var(--mc-surface);
    color: var(--mc-text);
    font-size: var(--mc-text-sm);
    font-weight: 600;
    cursor: pointer;
  }

  @media (max-width: 30rem) {
    .row {
      flex-direction: column;
    }

    .select-row {
      align-items: flex-start;
    }
  }
</style>
