<script lang="ts">
  import * as identityApi from '$contexts/identity/api';
  import { session } from '$contexts/identity/session.svelte';
  import { presentAuthError } from '$contexts/identity/messages';
  import type { SessionSummary } from '$contexts/identity/types';
  import Button from '$shared/ui/Button.svelte';
  import IconAlert from '$shared/ui/icons/IconAlert.svelte';

  const user = $derived(session.user);

  let sessions = $state<SessionSummary[]>([]);
  let loading = $state(true);
  let busy = $state(false);
  let error = $state<ReturnType<typeof presentAuthError> | null>(null);

  $effect(() => {
    void load();
  });

  async function load() {
    loading = true;
    try {
      sessions = await identityApi.listSessions();
    } catch (caught) {
      error = presentAuthError(caught);
    } finally {
      loading = false;
    }
  }

  async function signOutEverywhere() {
    busy = true;
    error = null;
    try {
      await identityApi.logoutEverywhere();
      await load();
    } catch (caught) {
      error = presentAuthError(caught);
    } finally {
      busy = false;
    }
  }

  function describe(s: SessionSummary): string {
    if (!s.user_agent) return 'Unknown device';
    if (/mobile/i.test(s.user_agent)) return 'Mobile browser';
    if (/chrome/i.test(s.user_agent)) return 'Chrome';
    if (/firefox/i.test(s.user_agent)) return 'Firefox';
    if (/safari/i.test(s.user_agent)) return 'Safari';
    if (/edg/i.test(s.user_agent)) return 'Edge';
    return 'Browser session';
  }
</script>

<svelte:head>
  <title>Security · Settings · MarketCompass</title>
</svelte:head>

<h1>Security</h1>

{#if error}
  <div class="banner error" role="alert">
    <span aria-hidden="true"><IconAlert /></span>
    <p>{error.message}</p>
  </div>
{/if}

<div class="row first">
  <div class="copy">
    <p class="label">Email &amp; password</p>
    <p class="hint">Set a unique password to protect your account.</p>
  </div>
  <span class="value">{user?.has_password ? 'Enabled' : 'Not set — sign in with Google'}</span>
</div>

<div class="row">
  <div class="copy">
    <p class="label">Google</p>
    <p class="hint">Sign in with your Google account instead of a password.</p>
  </div>
  <span class="value">
    {user?.linked_providers?.includes('google') ? 'Linked' : 'Not linked'}
  </span>
</div>

<div class="row">
  <div class="copy">
    <p class="label">Active sessions</p>
    <p class="hint">Devices currently signed in to your account.</p>
  </div>
  <Button variant="secondary" onclick={signOutEverywhere} loading={busy}>Sign out everywhere</Button
  >
</div>

{#if loading}
  <p class="hint indent">Loading…</p>
{:else if sessions.length === 0}
  <p class="hint indent">No active sessions.</p>
{:else}
  {#each sessions as s (s.id)}
    <div class="session">
      <div class="copy">
        <p class="label sm">
          {describe(s)}
          {#if s.is_current}<span class="badge">This device</span>{/if}
        </p>
        <p class="hint">
          {s.ip_address || 'Unknown IP'} · signed in {new Date(s.created_at).toLocaleString()}
        </p>
      </div>
    </div>
  {/each}
{/if}

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

  .session {
    display: flex;
    padding: var(--mc-space-3) var(--mc-space-4);
  }

  .copy {
    min-width: 0;
    max-width: 32rem;
  }

  .label {
    margin: 0;
    display: flex;
    align-items: center;
    gap: var(--mc-space-2);
    font-size: var(--mc-text-base);
    font-weight: 700;
  }

  .label.sm {
    font-size: var(--mc-text-sm);
  }

  .hint {
    margin: var(--mc-space-2) 0 0;
    font-size: var(--mc-text-sm);
    line-height: 1.6;
    color: var(--mc-text-muted);
  }

  .hint.indent {
    padding-left: var(--mc-space-4);
  }

  .value {
    flex: none;
    font-size: var(--mc-text-base);
    font-weight: 600;
    color: var(--mc-text);
    text-align: right;
  }

  .badge {
    padding: 0.0625rem 0.4375rem;
    border-radius: 999px;
    background: var(--mc-accent-weak);
    color: var(--mc-accent);
    font-size: var(--mc-text-xs);
    font-weight: 700;
  }

  .banner {
    display: flex;
    align-items: center;
    gap: var(--mc-space-2);
    margin-bottom: var(--mc-space-4);
    padding: 0.625rem 0.75rem;
    border-radius: var(--mc-radius);
    font-size: var(--mc-text-sm);
  }

  .banner p {
    margin: 0;
  }

  .banner.error {
    border: 1px solid color-mix(in srgb, var(--mc-danger) 40%, transparent);
    background: color-mix(in srgb, var(--mc-danger) 12%, transparent);
    color: var(--mc-text);
  }

  .banner.error span {
    color: var(--mc-danger);
  }

  @media (max-width: 30rem) {
    .row {
      flex-direction: column;
      align-items: flex-start;
      gap: var(--mc-space-2);
    }

    .value {
      text-align: left;
    }
  }
</style>
