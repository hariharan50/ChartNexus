<script lang="ts">
  import Button from '$shared/ui/Button.svelte';
  import IconArrowLeft from '$shared/ui/icons/IconArrowLeft.svelte';

  // Password reset needs an email adapter, which the backend does not have yet.
  // Rather than pretend to send a message, this states the situation plainly —
  // a form that silently does nothing is worse than no form.
</script>

<svelte:head>
  <title>Reset password · MarketCompass</title>
</svelte:head>

<header class="intro">
  <h1>Reset your password</h1>
  <p>Password reset by email is not available yet.</p>
</header>

<div class="note">
  <p>
    If you cannot sign in, contact
    <a href="mailto:support@marketcompass.app">support@marketcompass.app</a> and we will verify your identity
    and reset the account manually.
  </p>
  <p>
    If your account was created with Google, use <strong>Continue with Google</strong> on the sign-in
    page — it has no password to reset.
  </p>
</div>

<Button variant="secondary" full onclick={() => window.location.assign('/login')}>
  <IconArrowLeft />
  Back to sign in
</Button>

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

  .note {
    margin-bottom: var(--mc-space-4);
    padding: 0.75rem;
    border: 1px solid var(--mc-auth-border);
    border-radius: var(--mc-radius);
    background: var(--mc-auth-field);
    font-size: var(--mc-text-sm);
    color: var(--mc-text-muted);
    line-height: 1.55;
  }

  .note p {
    margin: 0;
  }

  .note p + p {
    margin-top: var(--mc-space-3);
  }

  .note a {
    color: var(--mc-brand);
  }
</style>
