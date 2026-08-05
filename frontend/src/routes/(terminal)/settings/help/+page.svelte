<script lang="ts">
  import SettingsIcon from '../components/SettingsIcon.svelte';

  interface Link {
    glyph: string;
    title: string;
    desc: string;
    href: string;
    external?: boolean;
  }

  const links: Link[] = [
    {
      glyph: 'book',
      title: 'Documentation',
      desc: 'Guides for options tools, indicators & the terminal',
      href: '#'
    },
    {
      glyph: 'lifebuoy',
      title: 'Contact support',
      desc: 'Reach the team — typically replies within a few hours',
      href: 'mailto:support@marketcompass.app',
      external: true
    },
    {
      glyph: 'bug',
      title: 'Report a bug',
      desc: 'Something off with the data or charts? Let us know',
      href: 'mailto:support@marketcompass.app?subject=Bug%20report',
      external: true
    },
    {
      glyph: 'users',
      title: 'Community',
      desc: 'Join other traders on the MarketCompass channel',
      href: '#'
    }
  ];
</script>

<svelte:head>
  <title>Help & Support · Settings · MarketCompass</title>
</svelte:head>

<h1>Help &amp; Support</h1>

<ul class="links">
  {#each links as link (link.title)}
    <li>
      <a
        class="row"
        href={link.href}
        rel={link.external ? 'noopener noreferrer' : undefined}
        target={link.external ? '_blank' : undefined}
      >
        <span class="ico"><SettingsIcon name={link.glyph} /></span>
        <span class="text">
          <span class="title">{link.title}</span>
          <span class="desc">{link.desc}</span>
        </span>
        <span class="chevron"><SettingsIcon name="chevron" /></span>
      </a>
    </li>
  {/each}
</ul>

<style>
  h1 {
    margin: 0 0 var(--mc-space-4);
    font-size: var(--mc-text-xl);
    font-weight: 700;
    letter-spacing: -0.01em;
  }

  .links {
    list-style: none;
    margin: 0 calc(-1 * var(--mc-space-4));
    padding: 0;
  }

  .row {
    display: flex;
    align-items: center;
    gap: var(--mc-space-4);
    padding: var(--mc-space-5) var(--mc-space-4);
    border-top: 1.5px solid var(--mc-border-strong);
    border-radius: var(--mc-radius);
    color: var(--mc-text);
    text-decoration: none;
    transition: background var(--mc-duration-fast) ease;
  }

  li:first-child .row {
    border-top: none;
  }

  .row:hover {
    background: var(--mc-surface-raised);
    text-decoration: none;
  }

  .ico {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 2.5rem;
    height: 2.5rem;
    flex: none;
    border-radius: var(--mc-radius);
    background: var(--mc-accent-weak);
    color: var(--mc-accent);
  }

  .ico :global(svg) {
    width: 1.25rem;
    height: 1.25rem;
  }

  .text {
    display: flex;
    flex-direction: column;
    gap: var(--mc-space-2);
    min-width: 0;
    flex: 1;
  }

  .title {
    font-size: var(--mc-text-base);
    font-weight: 700;
  }

  .desc {
    font-size: var(--mc-text-sm);
    color: var(--mc-text-muted);
  }

  .chevron {
    display: inline-flex;
    flex: none;
    width: 1.1rem;
    height: 1.1rem;
    color: var(--mc-text-subtle);
  }

  .chevron :global(svg) {
    width: 100%;
    height: 100%;
  }
</style>
