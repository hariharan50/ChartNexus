<script lang="ts">
  import { QueryClientProvider } from '@tanstack/svelte-query';
  import { page } from '$app/state';
  import { afterNavigate } from '$app/navigation';
  import { session } from '$contexts/identity/session.svelte';
  import { createQueryClient } from '$shared/api/query-client';
  import { theme } from '$shared/ui/theme.svelte';
  import IconBolt from '$shared/ui/icons/IconBolt.svelte';
  import IconSearch from '$shared/ui/icons/IconSearch.svelte';
  import IconChevronDown from '$shared/ui/icons/IconChevronDown.svelte';
  import IconMoon from '$shared/ui/icons/IconMoon.svelte';
  import IconSun from '$shared/ui/icons/IconSun.svelte';
  import IconChart from '$shared/ui/icons/IconChart.svelte';
  import IconTarget from '$shared/ui/icons/IconTarget.svelte';

  let { data, children } = $props();

  // One client per browser session. Created here (not at module scope) so an
  // SSR render never shares cache across requests.
  const queryClient = createQueryClient();

  // Seed the client store from the layout load so the header renders on the
  // first paint rather than after a round trip.
  $effect(() => {
    session.hydrate(data.user);
  });

  // Adopt the persisted theme once the browser is available.
  $effect(() => {
    theme.init();
  });

  const initials = $derived(
    (data.user?.display_name || data.user?.email || '?')
      .split(/[\s@.]+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((part: string) => part[0]?.toUpperCase() ?? '')
      .join('')
  );

  const shortName = $derived(
    (data.user?.display_name || data.user?.email || 'Account').split(/[\s@]/)[0]
  );

  // The menu structure the terminal will grow into. Only Dashboards and Option
  // Chain resolve today; the rest are stubs the routing work will fill in.
  type NavChild = { label: string; href: string; icon?: typeof IconChart };
  type NavItem = { label: string; href: string; children?: NavChild[] };

  const nav: NavItem[] = [
    {
      label: 'Dashboards',
      href: '/dashboard',
      children: [
        { label: 'Dashboard', href: '/dashboard', icon: IconChart },
        { label: 'Advance Dashboard', href: '/advanced-dashboard', icon: IconTarget },
        { label: 'Options', href: '/options', icon: IconChart }
      ]
    },
    {
      label: 'Options Lab',
      href: '/options',
      children: [
        { label: 'Open Interest', href: '/options/open-interest', icon: IconChart },
        { label: 'Multi OI Volume', href: '/options/multi-oi-volume', icon: IconChart },
        { label: 'PCR', href: '/options/pcr', icon: IconChart },
        { label: 'Max Pain', href: '/options/max-pain', icon: IconTarget },
        { label: 'Gamma Exposure', href: '/options/gamma-exposure', icon: IconChart }
      ]
    },
    { label: 'Future Lab', href: '/future-lab' },
    { label: 'Analyse', href: '/analyse' },
    { label: 'Smart Insights', href: '/smart-insights' },
    { label: 'Option Chain', href: '/option-chain' }
  ];

  function isActive(href: string): boolean {
    return page.url.pathname === href || page.url.pathname.startsWith(href + '/');
  }

  // Native <details> menus do not close one another or dismiss on an outside
  // click. We keep the whole header in `headerEl` and close every open menu on
  // an outside click, on Escape, and after any client-side navigation so only
  // one dropdown is ever visible at a time.
  let headerEl = $state<HTMLElement>();

  function closeMenus(except?: EventTarget | null) {
    if (!headerEl) return;
    for (const el of headerEl.querySelectorAll<HTMLDetailsElement>('details[open]')) {
      if (except && el.contains(except as Node)) continue;
      el.open = false;
    }
  }

  $effect(() => {
    const onPointerDown = (e: PointerEvent) => {
      if (!headerEl?.contains(e.target as Node)) closeMenus();
      else closeMenus(e.target);
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') closeMenus();
    };
    document.addEventListener('pointerdown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('pointerdown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  });

  afterNavigate(() => closeMenus());

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

<QueryClientProvider client={queryClient}>
  <div class="terminal">
    <header class="nav" bind:this={headerEl}>
    <div class="nav-left">
      <a class="brand" href="/dashboard">
        <span class="mark" aria-hidden="true"><IconBolt /></span>
        <span class="name">MarketCompass</span>
      </a>

      <nav aria-label="Primary">
        <ul>
          {#each nav as item (item.label)}
            <li>
              {#if item.children}
                <details class="nav-menu">
                  <summary class="nav-link" class:active={isActive(item.href)}>
                    {item.label}
                    <span class="caret" aria-hidden="true"><IconChevronDown /></span>
                  </summary>
                  <div class="submenu">
                    {#each item.children as child (child.href)}
                      <a
                        class="submenu-item"
                        class:active={isActive(child.href)}
                        href={child.href}
                      >
                        {#if child.icon}
                          {@const Icon = child.icon}
                          <span class="submenu-ico" aria-hidden="true"><Icon /></span>
                        {/if}
                        {child.label}
                      </a>
                    {/each}
                  </div>
                </details>
              {:else}
                <a class="nav-link" class:active={isActive(item.href)} href={item.href}>
                  {item.label}
                </a>
              {/if}
            </li>
          {/each}
        </ul>
      </nav>
    </div>

    <div class="nav-right">
      <form class="search" role="search" onsubmit={(e) => e.preventDefault()}>
        <span class="search-ico" aria-hidden="true"><IconSearch /></span>
        <input
          type="search"
          placeholder="Search symbol…"
          aria-label="Search symbol"
          value="NIFTY50"
        />
      </form>

      <button
        type="button"
        class="icon-btn"
        onclick={() => theme.toggle()}
        aria-label={theme.value === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
        title="Toggle theme"
      >
        {#if theme.value === 'dark'}<IconMoon />{:else}<IconSun />{/if}
      </button>

      <details class="account">
        <summary aria-label="Account menu">
          <span class="avatar" aria-hidden="true">{initials}</span>
          <span class="who">{shortName}</span>
          <span class="caret" aria-hidden="true"><IconChevronDown /></span>
        </summary>
        <div class="menu">
          <div class="menu-head">
            <p class="menu-name">{data.user?.display_name}</p>
            <p class="menu-email">{data.user?.email}</p>
          </div>
          <a class="menu-item" href="/settings/broker">Broker connection</a>
          <button class="menu-item" type="button" onclick={signOut} disabled={signingOut}>
            {signingOut ? 'Signing out…' : 'Sign out'}
          </button>
        </div>
      </details>
    </div>
  </header>

    <main class="content">
      {@render children()}
    </main>
  </div>
</QueryClientProvider>

<style>
  .terminal {
    display: flex;
    flex-direction: column;
    min-height: 100vh;
    min-height: 100dvh;
    background: var(--mc-bg);
  }

  .nav {
    position: sticky;
    top: 0;
    z-index: var(--mc-z-sticky);
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--mc-space-4);
    padding: 0.5rem var(--mc-space-6);
    border-bottom: 1px solid var(--mc-border);
    background: var(--mc-surface);
  }

  .nav-left,
  .nav-right {
    display: flex;
    align-items: center;
    gap: var(--mc-space-2);
  }

  .nav-left {
    gap: var(--mc-space-6);
    min-width: 0;
  }

  .brand {
    display: inline-flex;
    align-items: center;
    gap: var(--mc-space-2);
    color: var(--mc-text);
    text-decoration: none;
    flex: none;
  }

  .mark {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 1.875rem;
    height: 1.875rem;
    border-radius: var(--mc-radius);
    background: var(--mc-accent);
    color: #fff;
  }

  .mark :global(svg) {
    width: 1.15rem;
    height: 1.15rem;
  }

  .name {
    font-size: var(--mc-text-lg);
    font-weight: 700;
    letter-spacing: -0.02em;
  }

  nav ul {
    display: flex;
    align-items: center;
    gap: 0.125rem;
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .nav-link {
    display: inline-flex;
    align-items: center;
    gap: 0.25rem;
    padding: 0.4375rem 0.75rem;
    border-radius: var(--mc-radius);
    color: var(--mc-text-muted);
    font-size: var(--mc-text-sm);
    font-weight: 600;
    text-decoration: none;
    white-space: nowrap;
    transition:
      background var(--mc-duration-fast) ease,
      color var(--mc-duration-fast) ease;
  }

  .nav-link:hover {
    background: var(--mc-surface-raised);
    color: var(--mc-text);
    text-decoration: none;
  }

  .nav-link.active {
    background: var(--mc-accent-weak);
    color: var(--mc-accent);
  }

  .caret {
    display: inline-flex;
    opacity: 0.7;
  }

  .caret :global(svg) {
    width: 0.875rem;
    height: 0.875rem;
  }

  .nav-menu {
    position: relative;
  }

  .nav-menu summary.nav-link {
    cursor: pointer;
    list-style: none;
  }

  .nav-menu summary::-webkit-details-marker {
    display: none;
  }

  .nav-menu[open] summary .caret {
    transform: rotate(180deg);
  }

  .submenu {
    position: absolute;
    left: 0;
    top: calc(100% + 0.375rem);
    z-index: var(--mc-z-dropdown);
    display: flex;
    flex-direction: column;
    width: 15rem;
    max-width: calc(100vw - 2rem);
    padding: var(--mc-space-2);
    border: 1px solid var(--mc-border);
    border-radius: var(--mc-radius);
    background: var(--mc-surface);
    box-shadow: var(--mc-shadow);
  }

  .submenu-item {
    display: flex;
    align-items: center;
    gap: var(--mc-space-2);
    padding: 0.5rem var(--mc-space-2);
    border-radius: var(--mc-radius-sm);
    color: var(--mc-text);
    font-size: var(--mc-text-sm);
    font-weight: 600;
    text-decoration: none;
  }

  .submenu-item:hover {
    background: var(--mc-surface-raised);
    text-decoration: none;
  }

  .submenu-item.active {
    background: var(--mc-accent-weak);
    color: var(--mc-accent);
  }

  .submenu-ico {
    display: inline-flex;
    color: var(--mc-text-muted);
  }

  .submenu-item.active .submenu-ico {
    color: var(--mc-accent);
  }

  .submenu-ico :global(svg) {
    width: 1rem;
    height: 1rem;
  }

  .search {
    position: relative;
    display: flex;
    align-items: center;
  }

  .search-ico {
    position: absolute;
    left: 0.625rem;
    display: inline-flex;
    color: var(--mc-text-subtle);
    pointer-events: none;
  }

  .search-ico :global(svg) {
    width: 1rem;
    height: 1rem;
  }

  .search input {
    width: 11rem;
    height: var(--mc-control-h-sm);
    padding: 0 0.75rem 0 2rem;
    border: 1px solid var(--mc-border);
    border-radius: var(--mc-radius);
    background: var(--mc-surface-raised);
    color: var(--mc-text);
    font-size: var(--mc-text-sm);
  }

  .search input::placeholder {
    color: var(--mc-text-subtle);
  }

  .search input:focus-visible {
    outline: none;
    border-color: var(--mc-accent);
  }

  .icon-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: var(--mc-control-h-sm);
    height: var(--mc-control-h-sm);
    border: 1px solid var(--mc-border);
    border-radius: var(--mc-radius);
    background: var(--mc-surface-raised);
    color: var(--mc-text-muted);
    cursor: pointer;
    transition:
      color var(--mc-duration-fast) ease,
      border-color var(--mc-duration-fast) ease;
  }

  .icon-btn:hover {
    color: var(--mc-text);
    border-color: var(--mc-border-strong);
  }

  .icon-btn :global(svg) {
    width: 1.05rem;
    height: 1.05rem;
  }

  .account {
    position: relative;
  }

  .account summary {
    display: inline-flex;
    align-items: center;
    gap: var(--mc-space-2);
    height: var(--mc-control-h-sm);
    padding: 0 0.5rem 0 0.375rem;
    border: 1px solid transparent;
    border-radius: var(--mc-radius);
    cursor: pointer;
    list-style: none;
  }

  .account summary::-webkit-details-marker {
    display: none;
  }

  .account summary:hover {
    background: var(--mc-surface-raised);
  }

  .account[open] summary {
    background: var(--mc-surface-raised);
    border-color: var(--mc-border);
  }

  .avatar {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 1.75rem;
    height: 1.75rem;
    border-radius: 50%;
    background: var(--mc-accent);
    color: #fff;
    font-size: var(--mc-text-xs);
    font-weight: 700;
  }

  .who {
    font-size: var(--mc-text-sm);
    font-weight: 600;
  }

  .menu {
    position: absolute;
    right: 0;
    top: calc(100% + 0.375rem);
    z-index: var(--mc-z-dropdown);
    width: 15rem;
    padding: var(--mc-space-2);
    border: 1px solid var(--mc-border);
    border-radius: var(--mc-radius);
    background: var(--mc-surface);
    box-shadow: var(--mc-shadow);
  }

  .menu-head {
    padding: var(--mc-space-2) var(--mc-space-2) var(--mc-space-3);
    border-bottom: 1px solid var(--mc-border);
    margin-bottom: var(--mc-space-1);
  }

  .menu-name {
    margin: 0;
    font-size: var(--mc-text-sm);
    font-weight: 600;
  }

  .menu-email {
    margin: 0.125rem 0 0;
    font-size: var(--mc-text-xs);
    color: var(--mc-text-subtle);
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .menu-item {
    display: block;
    width: 100%;
    padding: 0.5rem var(--mc-space-2);
    border: none;
    border-radius: var(--mc-radius-sm);
    background: transparent;
    color: var(--mc-text);
    font-size: var(--mc-text-sm);
    text-align: left;
    text-decoration: none;
    cursor: pointer;
  }

  .menu-item:hover {
    background: var(--mc-surface-raised);
    text-decoration: none;
  }

  .menu-item:disabled {
    opacity: 0.6;
    cursor: default;
  }

  .content {
    flex: 1;
  }

  /* Wide-but-tight: pull the header in before anything has to disappear. */
  @media (max-width: 90rem) {
    .nav-left {
      gap: var(--mc-space-4);
    }

    .nav-link {
      padding: 0.4375rem 0.5rem;
    }

    nav ul {
      gap: 0;
    }
  }

  /* Reclaim the brand wordmark and search width so the primary nav survives. */
  @media (max-width: 72rem) {
    .name {
      display: none;
    }

    .search input {
      width: 8.5rem;
    }
  }

  /* Below the tablet range there is no room for the full menu bar, so collapse
     it. The account menu and search stay reachable. */
  @media (max-width: 60rem) {
    nav {
      display: none;
    }
  }

  @media (max-width: 40rem) {
    .nav {
      padding: 0.5rem var(--mc-space-4);
    }

    .search input {
      width: 7rem;
    }

    .who {
      display: none;
    }
  }
</style>
