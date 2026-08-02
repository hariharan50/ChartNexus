<script lang="ts">
  import { goto } from '$app/navigation';
  import { page } from '$app/state';
  import * as auth from '$contexts/identity/api';
  import { presentAuthError } from '$contexts/identity/messages';
  import { session } from '$contexts/identity/session.svelte';
  import Button from '$shared/ui/Button.svelte';
  import PasswordField from '$shared/ui/PasswordField.svelte';
  import TextField from '$shared/ui/TextField.svelte';
  import IconAlert from '$shared/ui/icons/IconAlert.svelte';
  import IconCheck from '$shared/ui/icons/IconCheck.svelte';
  import IconAt from '$shared/ui/icons/IconAt.svelte';
  import IconGoogle from '$shared/ui/icons/IconGoogle.svelte';

  let email = $state('');
  let password = $state('');
  let rememberMe = $state(true);

  let submitting = $state(false);
  let googlePending = $state(false);
  let error = $state<ReturnType<typeof presentAuthError> | null>(null);

  // Where to land after signing in. Only same-site paths are honoured, so a
  // crafted ?next= cannot bounce the user to another origin.
  const next = $derived.by(() => {
    const target = page.url.searchParams.get('next');
    return target?.startsWith('/') && !target.startsWith('//') ? target : '/dashboard';
  });

  // Set by the register flow, which ends here rather than at the dashboard.
  const justRegistered = $derived(page.url.searchParams.get('registered') === '1');

  const fieldError = (name: string) => (error?.field === name ? error.message : undefined);

  async function submit(event: SubmitEvent) {
    event.preventDefault();
    if (submitting) return;

    submitting = true;
    error = null;
    try {
      const result = await auth.login(email.trim(), password);
      session.hydrate(result.user);
      await goto(next, { invalidateAll: true });
    } catch (caught) {
      error = presentAuthError(caught);
      password = '';
    } finally {
      submitting = false;
    }
  }

  async function continueWithGoogle() {
    if (googlePending) return;

    googlePending = true;
    error = null;
    try {
      const { authorization_url } = await auth.startGoogleLogin(next);
      // A full navigation, not a router push: the next stop is Google's origin.
      window.location.assign(authorization_url);
    } catch (caught) {
      error = presentAuthError(caught);
      googlePending = false;
    }
  }
</script>

<svelte:head>
  <title>Sign in · MarketCompass</title>
  <meta name="description" content="Sign in to your MarketCompass account." />
</svelte:head>

<header class="intro">
  <h1>Welcome back</h1>
  <p>Sign in to your MarketCompass account to continue.</p>
</header>

{#if justRegistered && !error}
  <div class="banner success" role="status">
    <span class="banner-icon" aria-hidden="true"><IconCheck /></span>
    <div>
      <p>Account created. Sign in to continue.</p>
    </div>
  </div>
{/if}

{#if error && !error.field}
  <div class="banner" role="alert">
    <span class="banner-icon" aria-hidden="true"><IconAlert /></span>
    <div>
      <p>{error.message}</p>
      {#if error.action}
        <a href={error.action.href}>{error.action.label}</a>
      {/if}
    </div>
  </div>
{/if}

<form onsubmit={submit} novalidate>
  <TextField
    label="Email"
    bind:value={email}
    type="email"
    inputmode="email"
    autocomplete="username"
    placeholder="you@example.com"
    error={fieldError('email')}
    required
    autofocus
  >
    {#snippet icon()}
      <IconAt />
    {/snippet}
  </TextField>

  <PasswordField bind:value={password} error={fieldError('password')} required />

  <div class="row">
    <label class="remember">
      <input type="checkbox" bind:checked={rememberMe} />
      <span>Remember me</span>
    </label>
    <a class="muted-link" href="/forgot-password">Forgot password?</a>
  </div>

  <Button type="submit" full loading={submitting}>
    {submitting ? 'Signing in…' : 'Log In'}
  </Button>
</form>

<div class="divider"><span>or continue with</span></div>

<Button variant="secondary" full loading={googlePending} onclick={continueWithGoogle}>
  <IconGoogle />
  Continue with Google
</Button>

<p class="footer">
  Don't have an account?
  <a href="/register">Sign up free</a>
</p>

<style>
  .intro {
    margin-bottom: var(--mc-space-6);
  }

  h1 {
    margin: 0 0 0.375rem;
    font-size: 1.5rem;
    font-weight: 700;
    letter-spacing: -0.02em;
  }

  .intro p {
    margin: 0;
    color: var(--mc-text-muted);
    font-size: var(--mc-text-sm);
  }

  form {
    display: flex;
    flex-direction: column;
    gap: 0.875rem;
  }

  .row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--mc-space-4);
  }

  .remember {
    display: inline-flex;
    align-items: center;
    gap: 0.4375rem;
    font-size: var(--mc-text-sm);
    color: var(--mc-text-muted);
    cursor: pointer;
  }

  .remember input {
    width: 0.875rem;
    height: 0.875rem;
    accent-color: var(--mc-brand);
    cursor: pointer;
  }

  .muted-link {
    font-size: var(--mc-text-sm);
    color: var(--mc-brand);
    font-weight: 500;
  }

  .banner {
    display: flex;
    gap: var(--mc-space-2);
    margin-bottom: var(--mc-space-4);
    padding: 0.625rem 0.75rem;
    font-size: var(--mc-text-sm);
    line-height: 1.45;
    border: 1px solid color-mix(in srgb, var(--mc-danger) 40%, transparent);
    border-radius: var(--mc-radius);
    background: color-mix(in srgb, var(--mc-danger) 12%, transparent);
  }

  .banner-icon {
    color: var(--mc-danger);
    flex-shrink: 0;
    padding-top: 0.1rem;
  }

  /* Same shape as the error banner, recoloured — this one is good news.
     --mc-live is the palette's green; the auth surface is dark in both themes,
     so it needs no light-theme counterpart. */
  .banner.success {
    border-color: color-mix(in srgb, var(--mc-live) 40%, transparent);
    background: color-mix(in srgb, var(--mc-live) 12%, transparent);
  }

  .banner.success .banner-icon {
    color: var(--mc-live);
  }

  .banner p {
    margin: 0;
  }

  .banner a {
    display: inline-block;
    margin-top: var(--mc-space-1);
    color: var(--mc-brand);
  }

  .divider {
    display: flex;
    align-items: center;
    gap: var(--mc-space-3);
    margin: var(--mc-space-4) 0 var(--mc-space-3);
    color: var(--mc-text-subtle);
    font-size: var(--mc-text-xs);
  }

  .divider::before,
  .divider::after {
    content: '';
    flex: 1;
    height: 1px;
    background: var(--mc-auth-border);
  }

  .footer {
    margin: var(--mc-space-6) 0 0;
    text-align: center;
    font-size: var(--mc-text-sm);
    color: var(--mc-text-muted);
  }

  .footer a {
    color: var(--mc-brand);
    font-weight: 600;
  }
</style>
