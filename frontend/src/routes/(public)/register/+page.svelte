<script lang="ts">
  import * as auth from '$contexts/identity/api';
  import { describePasswordPolicy, presentAuthError } from '$contexts/identity/messages';
  import { session } from '$contexts/identity/session.svelte';
  import Button from '$shared/ui/Button.svelte';
  import PasswordField from '$shared/ui/PasswordField.svelte';
  import PhoneField from '$shared/ui/PhoneField.svelte';
  import TextField from '$shared/ui/TextField.svelte';
  import IconAlert from '$shared/ui/icons/IconAlert.svelte';
  import IconAt from '$shared/ui/icons/IconAt.svelte';
  import IconGoogle from '$shared/ui/icons/IconGoogle.svelte';
  import IconUser from '$shared/ui/icons/IconUser.svelte';
  import { isValidIndianMobile, toE164 } from '$shared/validation/phone';

  const MIN_PASSWORD_LENGTH = 12;

  let displayName = $state('');
  let email = $state('');
  let phone = $state('');
  let password = $state('');
  let confirmPassword = $state('');

  let submitting = $state(false);
  let googlePending = $state(false);
  let error = $state<ReturnType<typeof presentAuthError> | null>(null);

  // Checked as the user types so the server never has to reject length alone.
  const tooShort = $derived(password.length > 0 && password.length < MIN_PASSWORD_LENGTH);
  // Only complain once the second field has been typed into, so the mismatch
  // does not flash while the user is still on their first keystroke.
  const mismatch = $derived(confirmPassword.length > 0 && confirmPassword !== password);
  // Same "wait until they have typed something" rule as the password mismatch.
  const phoneIncomplete = $derived(phone.length > 0 && !isValidIndianMobile(phone));
  const canSubmit = $derived(
    email.trim().length > 0 &&
      isValidIndianMobile(phone) &&
      password.length >= MIN_PASSWORD_LENGTH &&
      confirmPassword === password &&
      !submitting
  );

  const fieldError = (name: string) => (error?.field === name ? error.message : undefined);

  async function submit(event: SubmitEvent) {
    event.preventDefault();
    if (!canSubmit) return;

    submitting = true;
    error = null;
    try {
      await auth.register({
        email: email.trim(),
        password,
        phone: toE164(phone),
        displayName: displayName.trim()
      });
      // Registering signs the account in, but the flow deliberately ends at the
      // sign-in page — so drop that session rather than leaving the new user
      // authenticated on a form asking them to authenticate. signOut clears
      // locally even if the network call fails, then redirects.
      await session.signOut('/login?registered=1');
    } catch (caught) {
      error = presentAuthError(caught);
    } finally {
      submitting = false;
    }
  }

  async function continueWithGoogle() {
    if (googlePending) return;

    googlePending = true;
    error = null;
    try {
      const { authorization_url } = await auth.startGoogleLogin('/dashboard');
      window.location.assign(authorization_url);
    } catch (caught) {
      error = presentAuthError(caught);
      googlePending = false;
    }
  }
</script>

<svelte:head>
  <title>Create an account · MarketCompass</title>
</svelte:head>

<header class="intro">
  <h1>Create your account</h1>
  <p>Start analysing NIFTY and SENSEX in minutes.</p>
</header>

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
    label="Name"
    bind:value={displayName}
    autocomplete="name"
    placeholder="Your name"
    autofocus
  >
    {#snippet icon()}
      <IconUser />
    {/snippet}
  </TextField>

  <TextField
    label="Email"
    bind:value={email}
    type="email"
    inputmode="email"
    autocomplete="username"
    placeholder="you@example.com"
    error={fieldError('email')}
    required
  >
    {#snippet icon()}
      <IconAt />
    {/snippet}
  </TextField>

  <PhoneField
    bind:value={phone}
    error={fieldError('phone') ??
      (phoneIncomplete ? 'Enter a 10-digit Indian mobile number.' : undefined)}
    required
  />

  <div>
    <PasswordField
      bind:value={password}
      label="Password"
      placeholder="Create a password"
      autocomplete="new-password"
      error={fieldError('password')}
      required
    />
    <p class="hint" class:warn={tooShort}>{describePasswordPolicy(MIN_PASSWORD_LENGTH)}</p>
  </div>

  <PasswordField
    bind:value={confirmPassword}
    label="Confirm password"
    placeholder="Re-enter your password"
    autocomplete="new-password"
    error={mismatch ? 'Both passwords must match.' : undefined}
    required
  />

  <Button type="submit" full loading={submitting} disabled={!canSubmit}>
    {submitting ? 'Creating account…' : 'Create account'}
  </Button>
</form>

<div class="divider"><span>or continue with</span></div>

<Button variant="secondary" full loading={googlePending} onclick={continueWithGoogle}>
  <IconGoogle />
  Continue with Google
</Button>

<p class="terms">
  By creating an account you agree that MarketCompass is analytics software and does not provide
  investment advice.
</p>

<p class="footer">
  Already have an account?
  <a href="/login">Sign in</a>
</p>

<style>
  .intro {
    margin-bottom: var(--mc-space-5, 1.25rem);
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

  .hint {
    margin: 0.375rem 0 0;
    font-size: var(--mc-text-xs);
    color: var(--mc-text-subtle);
  }

  .hint.warn {
    color: var(--mc-warning);
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

  .terms {
    margin: var(--mc-space-4) 0 0;
    font-size: var(--mc-text-xs);
    line-height: 1.5;
    color: var(--mc-text-subtle);
  }

  .footer {
    margin: var(--mc-space-3) 0 0;
    text-align: center;
    font-size: var(--mc-text-sm);
    color: var(--mc-text-muted);
  }

  .footer a {
    color: var(--mc-brand);
    font-weight: 600;
  }
</style>
