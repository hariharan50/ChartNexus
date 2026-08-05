<script lang="ts">
  import { session } from '$contexts/identity/session.svelte';

  const user = $derived(session.user);

  const memberSince = $derived(
    user?.created_at
      ? new Date(user.created_at).toLocaleDateString(undefined, {
          year: 'numeric',
          month: 'long',
          day: 'numeric'
        })
      : '—'
  );

  const loginMethod = $derived(
    user?.linked_providers?.includes('google') && user?.has_password
      ? 'Password & Google'
      : user?.linked_providers?.includes('google')
        ? 'Google'
        : user?.has_password
          ? 'Password'
          : '—'
  );
</script>

<svelte:head>
  <title>Personal Info · Settings · MarketCompass</title>
</svelte:head>

<h1>Personal Info</h1>

<div class="row first">
  <div class="copy">
    <p class="label">Display name</p>
    <p class="hint">The name shown across the terminal.</p>
  </div>
  <span class="value">{user?.display_name || '—'}</span>
</div>

<div class="row">
  <div class="copy">
    <p class="label">Email address</p>
    <p class="hint">The email address associated with your account.</p>
  </div>
  <div class="value-stack">
    <span class="value mono">{user?.email || '—'}</span>
    {#if user && !user.email_verified}
      <span class="unverified">Unverified</span>
    {/if}
  </div>
</div>

<div class="row">
  <div class="copy">
    <p class="label">Sign-in method</p>
    <p class="hint">How you authenticate into MarketCompass.</p>
  </div>
  <span class="value">{loginMethod}</span>
</div>

<div class="row">
  <div class="copy">
    <p class="label">Member since</p>
    <p class="hint">When your account was created.</p>
  </div>
  <span class="value">{memberSince}</span>
</div>

<div class="row">
  <div class="copy">
    <p class="label">Status</p>
    <p class="hint">Your account's current standing.</p>
  </div>
  <span class="value capitalize">{user?.status.replace('_', ' ') || '—'}</span>
</div>

<style>
  h1 {
    margin: 0 0 var(--mc-space-4);
    font-size: var(--mc-text-xl);
    font-weight: 700;
    letter-spacing: -0.01em;
  }

  .row {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: var(--mc-space-6);
    margin: 0 calc(-1 * var(--mc-space-4));
    padding: var(--mc-space-6) var(--mc-space-4);
    border-top: 1.5px solid var(--mc-border-strong);
    border-radius: var(--mc-radius);
    transition: background var(--mc-duration-fast) ease;
  }

  .row:hover {
    background: var(--mc-surface-raised);
  }

  .row.first {
    margin-top: var(--mc-space-4);
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

  .value {
    flex: none;
    font-size: var(--mc-text-base);
    font-weight: 600;
    color: var(--mc-text);
    text-align: right;
  }

  .value.mono {
    font-family: var(--mc-font-mono);
    font-weight: 500;
  }

  .value.capitalize {
    text-transform: capitalize;
  }

  .value-stack {
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: 0.1875rem;
  }

  .unverified {
    font-size: var(--mc-text-xs);
    font-weight: 700;
    color: var(--mc-danger);
  }

  @media (max-width: 30rem) {
    .row {
      flex-direction: column;
      align-items: flex-start;
      gap: var(--mc-space-2);
    }

    .value,
    .value-stack {
      text-align: left;
      align-items: flex-start;
    }
  }
</style>
