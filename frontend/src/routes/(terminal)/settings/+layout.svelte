<script lang="ts">
  import { page } from '$app/state';

  let { children } = $props();

  const nav = [
    { label: 'Personal Info', href: '/settings/profile' },
    { label: 'Security', href: '/settings/security' },
    { label: 'Notifications', href: '/settings/notifications' },
    { label: 'Broker Connect', href: '/settings/broker' },
    { label: 'Global Settings', href: '/settings/global' },
    { label: 'My Plans', href: '/settings' },
    { label: 'Help & Support', href: '/settings/help' }
  ];

  function isActive(href: string): boolean {
    if (href === '/settings') return page.url.pathname === '/settings';
    return page.url.pathname === href || page.url.pathname.startsWith(href + '/');
  }
</script>

<div class="page">
  <h1 class="page-title">Account Settings</h1>

  <div class="card">
    <nav class="nav" aria-label="Settings sections">
      {#each nav as item (item.href)}
        <a class="nav-item" class:active={isActive(item.href)} href={item.href}>{item.label}</a>
      {/each}
    </nav>

    <div class="content">
      {@render children()}
    </div>
  </div>
</div>

<style>
  .page {
    max-width: 84rem;
    margin: 0 auto;
    padding: var(--mc-space-6) var(--mc-space-6) var(--mc-space-8);
  }

  .page-title {
    margin: 0 0 var(--mc-space-4);
    font-size: var(--mc-text-2xl);
    font-weight: 700;
    letter-spacing: -0.01em;
  }

  .card {
    display: grid;
    grid-template-columns: 14rem 1px minmax(0, 1fr);
    align-items: start;
    background: var(--mc-surface);
    border: 1px solid var(--mc-border);
    border-radius: var(--mc-radius-lg);
    box-shadow: var(--mc-shadow);
    overflow: hidden;
  }

  .card::before {
    content: '';
    grid-column: 2;
    grid-row: 1;
    align-self: stretch;
    background: var(--mc-border);
  }

  .nav {
    grid-column: 1;
    position: sticky;
    top: var(--mc-space-6);
    display: flex;
    flex-direction: column;
    gap: 0.125rem;
    padding: var(--mc-space-5) var(--mc-space-3);
  }

  .nav-item {
    padding: 0.625rem var(--mc-space-4);
    border-radius: 999px;
    color: var(--mc-text-muted);
    font-size: var(--mc-text-sm);
    font-weight: 600;
    text-decoration: none;
    transition:
      background var(--mc-duration-fast) ease,
      color var(--mc-duration-fast) ease;
  }

  .nav-item:hover {
    color: var(--mc-text);
    text-decoration: none;
  }

  .nav-item.active {
    background: var(--mc-accent-weak);
    color: var(--mc-accent);
    font-weight: 700;
  }

  .content {
    grid-column: 3;
    min-width: 0;
    padding: var(--mc-space-8) var(--mc-space-10);
  }

  @media (max-width: 60rem) {
    .card {
      grid-template-columns: 1fr;
    }

    .card::before {
      display: none;
    }

    .nav {
      position: static;
      grid-column: 1;
      flex-direction: row;
      flex-wrap: wrap;
      gap: var(--mc-space-2);
      border-bottom: 1px solid var(--mc-border);
      padding: var(--mc-space-4);
    }

    .content {
      grid-column: 1;
      padding: var(--mc-space-5) var(--mc-space-4);
    }
  }

  @media (max-width: 40rem) {
    .page {
      padding: var(--mc-space-4);
    }
  }
</style>
