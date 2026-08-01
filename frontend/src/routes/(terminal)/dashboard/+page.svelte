<script lang="ts">
  import { page } from '$app/state';
  import { session } from '$contexts/identity/session.svelte';

  // Placeholder until the market-data context lands. It exists so the auth
  // flow has a real destination that proves the session round-tripped.
  const isNew = $derived(page.url.searchParams.get('welcome') === '1');
  const user = $derived(session.user);
</script>

<svelte:head>
  <title>Dashboard · MarketCompass</title>
</svelte:head>

<section>
  <h1>{isNew ? 'Welcome to MarketCompass' : 'Welcome back'}</h1>
  <p class="lead">
    Signed in as <strong>{user?.email}</strong>.
  </p>

  <dl class="facts">
    <div>
      <dt>Roles</dt>
      <dd>{user?.roles.join(', ')}</dd>
    </div>
    <div>
      <dt>Sign-in method</dt>
      <dd>
        {user?.linked_providers.length ? user.linked_providers.join(', ') : 'password'}
      </dd>
    </div>
    <div>
      <dt>Email verified</dt>
      <dd>{user?.email_verified ? 'Yes' : 'Not yet'}</dd>
    </div>
  </dl>

  <p class="note">
    The terminal itself is still being built — market data, option chain analytics and signals land
    with the next contexts.
  </p>
</section>

<style>
  section {
    max-width: 46rem;
    padding: var(--mc-space-6) var(--mc-space-4);
  }

  h1 {
    margin: 0 0 0.25rem;
    font-size: var(--mc-text-xl);
    font-weight: 700;
    letter-spacing: -0.01em;
  }

  .lead {
    margin: 0 0 var(--mc-space-4);
    font-size: var(--mc-text-sm);
    color: var(--mc-text-muted);
  }

  .facts {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(10rem, 1fr));
    gap: var(--mc-space-2);
    margin: 0 0 var(--mc-space-4);
  }

  .facts div {
    padding: 0.75rem;
    border: 1px solid var(--mc-border);
    border-radius: var(--mc-radius);
    background: var(--mc-surface);
  }

  dt {
    font-size: var(--mc-text-xs);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--mc-text-subtle);
  }

  dd {
    margin: 0.1875rem 0 0;
    font-size: var(--mc-text-sm);
    font-weight: 600;
  }

  .note {
    margin: 0;
    color: var(--mc-text-subtle);
    font-size: var(--mc-text-xs);
  }
</style>
