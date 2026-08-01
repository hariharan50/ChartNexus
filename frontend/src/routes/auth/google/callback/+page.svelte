<script lang="ts">
  import { goto } from '$app/navigation';
  import { page } from '$app/state';
  import * as auth from '$contexts/identity/api';
  import { presentAuthError } from '$contexts/identity/messages';
  import { session } from '$contexts/identity/session.svelte';
  import Button from '$shared/ui/Button.svelte';
  import IconAlert from '$shared/ui/icons/IconAlert.svelte';

  /**
   * Where Google returns the user (MC_GOOGLE_REDIRECT_URI).
   *
   * The `code` lands in the browser's address bar, so this page hands it
   * straight to the API and replaces the history entry — a code left in history
   * can be replayed from the back button or leaked in a referrer.
   */

  let error = $state<ReturnType<typeof presentAuthError> | null>(null);

  $effect(() => {
    void complete();
  });

  async function complete() {
    const params = page.url.searchParams;

    // The user pressed "cancel" on Google's consent screen.
    if (params.get('error')) {
      error = {
        message:
          params.get('error') === 'access_denied'
            ? 'Google sign-in was cancelled.'
            : 'Google could not complete this sign-in.'
      };
      return;
    }

    const code = params.get('code');
    const state = params.get('state');
    if (!code || !state) {
      error = { message: 'This sign-in link is incomplete. Start again.' };
      return;
    }

    try {
      const result = await auth.completeGoogleLogin(code, state);
      session.hydrate(result.user);
      // replaceState so the back button cannot return to a spent code.
      await goto(result.is_new_user ? '/dashboard?welcome=1' : '/dashboard', {
        replaceState: true,
        invalidateAll: true
      });
    } catch (caught) {
      error = presentAuthError(caught);
    }
  }
</script>

<svelte:head>
  <title>Signing in · MarketCompass</title>
  <meta name="robots" content="noindex" />
</svelte:head>

{#if error}
  <div class="state">
    <span class="icon error" aria-hidden="true"><IconAlert /></span>
    <h1>Sign-in failed</h1>
    <p>{error.message}</p>
    <Button variant="secondary" full onclick={() => goto('/login', { replaceState: true })}>
      Back to sign in
    </Button>
  </div>
{:else}
  <div class="state" aria-live="polite">
    <span class="spinner" aria-hidden="true"></span>
    <h1>Signing you in…</h1>
    <p>Completing your Google sign-in.</p>
  </div>
{/if}

<style>
  /* This route sits outside the (public) split-screen group, so it centres
     itself rather than inheriting a form column. */
  .state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: var(--mc-space-3);
    min-height: 80vh;
    max-width: 22rem;
    margin: 0 auto;
    padding: var(--mc-space-6);
    text-align: center;
  }

  h1 {
    margin: var(--mc-space-2) 0 0;
    font-size: 1.5rem;
    font-weight: 700;
  }

  p {
    margin: 0 0 var(--mc-space-4);
    color: var(--mc-text-muted);
  }

  .icon.error {
    color: var(--mc-danger);
  }

  .spinner {
    width: 2rem;
    height: 2rem;
    border: 2px solid var(--mc-auth-border);
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
