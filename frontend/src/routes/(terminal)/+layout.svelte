<script lang="ts">
  import { session } from '$contexts/identity/session.svelte';
  import Button from '$shared/ui/Button.svelte';
  import IconBolt from '$shared/ui/icons/IconBolt.svelte';

  let { data, children } = $props();

  // Seed the client store from the layout load so the header renders on the
  // first paint rather than after a round trip.
  $effect(() => {
    session.hydrate(data.user);
  });

  const initials = $derived(
    (data.user?.display_name || data.user?.email || '?')
      .split(/[\s@.]+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((part: string) => part[0]?.toUpperCase() ?? '')
      .join('')
  );

  let signingOut = $state(false);

  async function signOut() {
    signingOut = true;
    try {
      await session.signOut();
    } finally {
      signingOut = false;
    }
  }
</script>

<div class="terminal">
  <header>
    <a class="brand" href="/dashboard">
      <span class="mark" aria-hidden="true"><IconBolt /></span>
      <span class="name">MarketCompass</span>
    </a>

    <div class="account">
      <span class="avatar" aria-hidden="true">{initials}</span>
      <div class="who">
        <p class="display-name">{data.user?.display_name}</p>
        <p class="email">{data.user?.email}</p>
      </div>
      <Button variant="ghost" onclick={signOut} loading={signingOut}>Sign out</Button>
    </div>
  </header>

  <div class="content">
    {@render children()}
  </div>
</div>

<style>
  .terminal {
    display: flex;
    flex-direction: column;
    min-height: 100vh;
    min-height: 100dvh;
    background: var(--mc-bg);
  }

  header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--mc-space-4);
    padding: 0.5rem var(--mc-space-4);
    border-bottom: 1px solid var(--mc-border);
    background: var(--mc-surface);
  }

  .brand {
    display: inline-flex;
    align-items: center;
    gap: var(--mc-space-2);
    color: var(--mc-text);
    text-decoration: none;
  }

  .mark {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 1.625rem;
    height: 1.625rem;
    border-radius: var(--mc-radius-sm);
    background: var(--mc-brand);
    color: var(--mc-on-brand);
  }

  .name {
    font-size: var(--mc-text-base);
    font-weight: 700;
    letter-spacing: -0.01em;
  }

  .account {
    display: flex;
    align-items: center;
    gap: var(--mc-space-2);
  }

  .avatar {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 1.625rem;
    height: 1.625rem;
    border-radius: 50%;
    background: var(--mc-brand-weak);
    border: 1px solid var(--mc-brand);
    color: var(--mc-brand);
    font-size: var(--mc-text-xs);
    font-weight: 700;
  }

  .who {
    line-height: 1.25;
  }

  .display-name {
    margin: 0;
    font-size: var(--mc-text-xs);
    font-weight: 600;
  }

  .email {
    margin: 0;
    font-size: var(--mc-text-xs);
    color: var(--mc-text-subtle);
  }

  .content {
    flex: 1;
  }

  @media (max-width: 40rem) {
    .who {
      display: none;
    }
  }
</style>
