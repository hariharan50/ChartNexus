<script lang="ts">
  import { page } from '$app/state';
  import OptionsLabIcon from './OptionsLabIcon.svelte';

  interface Item {
    label: string;
    glyph: string;
    href: string;
    isNew?: boolean;
  }
  interface Section {
    title: string;
    items: Item[];
  }

  const sections: Section[] = [
    {
      title: 'Price Tools',
      items: [
        { label: 'Future Dashboard', glyph: 'gauge', href: '/future-lab/dashboard' },
        { label: 'Market Movers', glyph: 'trend', href: '/future-lab/market-movers', isNew: true },
        { label: 'Future Heatmap', glyph: 'grid', href: '/future-lab/heatmap' }
      ]
    },
    {
      title: 'OI Tools',
      items: [
        { label: 'Future Intraday', glyph: 'activity', href: '/future-lab/intraday' },
        { label: 'Price vs OI', glyph: 'bars', href: '/future-lab/price-vs-oi' },
        { label: 'Future Sentiment Cycle', glyph: 'cycle', href: '/future-lab/sentiment-cycle' }
      ]
    }
  ];

  function isActive(href: string): boolean {
    return page.url.pathname === href;
  }
</script>

<div class="panel">
  <div class="panel-head">
    <p class="panel-title">Future Lab</p>
    <p class="panel-sub">Futures analytics toolkit · All modules in development</p>
  </div>

  <div class="cols">
    {#each sections as section (section.title)}
      <div class="col">
        <p class="col-title">{section.title}</p>
        <ul>
          {#each section.items as item (item.label)}
            <li>
              <a class="item" class:active={isActive(item.href)} href={item.href}>
                <span class="ico"><OptionsLabIcon name={item.glyph} /></span>
                <span class="label">{item.label}</span>
                {#if item.isNew}<span class="new-badge" aria-label="New">N</span>{/if}
              </a>
            </li>
          {/each}
        </ul>
      </div>
    {/each}
  </div>
</div>

<style>
  .panel {
    position: absolute;
    left: 0;
    top: calc(100% + 0.5rem);
    z-index: var(--mc-z-dropdown);
    width: min(24rem, calc(100vw - 2rem));
    padding: var(--mc-space-5) var(--mc-space-5) var(--mc-space-4);
    border: 1px solid var(--mc-border);
    border-radius: var(--mc-radius-lg);
    background: var(--mc-surface);
    box-shadow: var(--mc-shadow-lg, var(--mc-shadow));
  }

  .panel-head {
    padding-bottom: var(--mc-space-4);
    margin-bottom: var(--mc-space-4);
    border-bottom: 1px solid var(--mc-border);
  }

  .panel-title {
    margin: 0;
    font-size: var(--mc-text-xs);
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--mc-text-subtle);
  }

  .panel-sub {
    margin: 0.3125rem 0 0;
    font-size: var(--mc-text-sm);
    color: var(--mc-text-muted);
  }

  .cols {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: var(--mc-space-5);
  }

  .col {
    min-width: 0;
  }

  .col + .col {
    padding-left: var(--mc-space-5);
    border-left: 1px solid var(--mc-border);
  }

  .col-title {
    margin: 0 0 var(--mc-space-3);
    padding: 0 0.625rem;
    font-size: var(--mc-text-xs);
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--mc-text-subtle);
  }

  ul {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }

  .item {
    display: flex;
    align-items: center;
    gap: var(--mc-space-3);
    padding: 0.625rem;
    border-radius: var(--mc-radius);
    color: var(--mc-text);
    font-size: var(--mc-text-sm);
    font-weight: 600;
    text-decoration: none;
    line-height: 1.3;
  }

  .item:hover {
    background: var(--mc-surface-raised);
    text-decoration: none;
  }

  .item.active {
    background: var(--mc-accent-weak);
    color: var(--mc-accent);
  }

  .ico {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 1.25rem;
    height: 1.25rem;
    flex: none;
    color: var(--mc-text-muted);
  }

  .item:hover .ico,
  .item.active .ico {
    color: var(--mc-accent);
  }

  .label {
    min-width: 0;
    flex: 1;
  }

  .new-badge {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 1.125rem;
    height: 1.125rem;
    flex: none;
    border-radius: 0.25rem;
    background: var(--mc-live);
    color: #fff;
    font-size: 0.625rem;
    font-weight: 700;
  }

  @media (max-width: 30rem) {
    .panel {
      width: calc(100vw - 2rem);
    }

    .cols {
      grid-template-columns: 1fr;
    }

    .col + .col {
      padding-left: 0;
      padding-top: var(--mc-space-4);
      margin-top: var(--mc-space-1);
      border-left: none;
      border-top: 1px solid var(--mc-border);
    }
  }
</style>
