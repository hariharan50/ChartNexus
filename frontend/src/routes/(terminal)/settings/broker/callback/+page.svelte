<script lang="ts">
  import { goto } from '$app/navigation';
  import { page } from '$app/state';
  import * as broker from '$contexts/broker-connections/api';
  import { presentAuthError } from '$contexts/identity/messages';
  import Button from '$shared/ui/Button.svelte';
  import IconAlert from '$shared/ui/icons/IconAlert.svelte';

  /**
   * Where FYERS returns the user (MC_BROKER_FYERS_REDIRECT_URI).
   *
   * The auth code lands in the address bar, so it is handed to the API
   * immediately and the history entry is replaced — a code left in history can
   * be replayed from the back button or leaked in a referrer.
   */

  let error = $state<ReturnType<typeof presentAuthError> | null>(null);

  $effect(() => {
    void complete();
  });

  async function complete() {
    const params = page.url.searchParams;

    if (params.get('error')) {
      error = { message: 'The broker cancelled this connection.' };
      return;
    }

    // FYERS uses `auth_code`; `code` is accepted as a fallback.
    const code = params.get('auth_code') ?? params.get('code');
    const state = params.get('state');
    if (!code || !state) {
      error = { message: 'This connection link is incomplete. Start again.' };
      return;
    }

    try {
      await broker.completeConnect(code, state);
      await goto('/settings/broker?connected=1', { replaceState: true, invalidateAll: true });
    } catch (caught) {
      error = presentAuthError(caught);
    }
  }
</script>

<svelte:head>
  <title>Connecting broker · MarketCompass</title>
  <meta name="robots" content="noindex" />
</svelte:head>

<div class="state">
  {#if error}
    <span class="icon" aria-hidden="true"><IconAlert /></span>
    <h1>Connection failed</h1>
    <p>{error.message}</p>
    <Button variant="secondary" onclick={() => goto('/settings/broker', { replaceState: true })}>
      Back to broker settings
    </Button>
  {:else}
    <span class="spinner" aria-hidden="true"></span>
    <h1>Connecting your broker…</h1>
    <p>Exchanging the authorisation code.</p>
  {/if}
</div>

<style>
  .state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: var(--mc-space-3);
    min-height: 60vh;
    max-width: 22rem;
    margin: 0 auto;
    padding: var(--mc-space-6);
    text-align: center;
  }

  h1 {
    margin: var(--mc-space-2) 0 0;
    font-size: var(--mc-text-lg);
    font-weight: 700;
  }

  p {
    margin: 0 0 var(--mc-space-3);
    font-size: var(--mc-text-sm);
    color: var(--mc-text-muted);
  }

  .icon {
    color: var(--mc-danger);
  }

  .spinner {
    width: 1.75rem;
    height: 1.75rem;
    border: 2px solid var(--mc-border);
    border-top-color: var(--mc-brand);
    border-radius: 50%;
    animation: spin 800ms linear infinite;
  }

  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }
</style>
