<script lang="ts">
  import { page } from '$app/state';
  import OptionsLabIcon from './OptionsLabIcon.svelte';

  interface Item {
    label: string;
    glyph: string;
    href: string;
  }
  interface Section {
    title: string;
    items: Item[];
  }

  const sections: Section[] = [
    {
      title: 'OI Tools',
      items: [
        { label: 'Open Interest', glyph: 'layers', href: '/options/open-interest' },
        { label: 'Multi OI & Volume', glyph: 'bars', href: '/options/multi-oi-volume' },
        { label: 'Put-Call Ratio', glyph: 'scale', href: '/options/pcr' },
        { label: 'Max Pain', glyph: 'target', href: '/options/max-pain' },
        { label: 'Gamma Exposure', glyph: 'activity', href: '/options/gamma-exposure' }
      ]
    },
    {
      title: 'Popular Tools',
      items: [
        { label: 'PE-CE Difference', glyph: 'diff', href: '/options/pe-ce-difference' },
        { label: 'Timeseries', glyph: 'trend', href: '/options/timeseries' },
        { label: 'Strategy Chart', glyph: 'strategy', href: '/options/strategy-chart' },
        { label: 'Smart OI', glyph: 'sparkle', href: '/options/smart-oi' },
        { label: 'Vega Analysis', glyph: 'flow', href: '/options/vega-analysis' }
      ]
    },
    {
      title: 'Price Tools',
      items: [
        { label: 'ATM Straddle Chart', glyph: 'straddle', href: '/options/atm-straddle' },
        { label: 'Premium Decay', glyph: 'timer', href: '/options/premium-decay' },
        { label: 'Price vs OI', glyph: 'trend', href: '/options/price-vs-oi' },
        { label: 'MultiStrike Chart', glyph: 'bars', href: '/options/multistrike' },
        { label: 'Multi-Straddle Chart', glyph: 'straddle', href: '/options/multi-straddle' }
      ]
    },
    {
      title: 'IV Tools',
      items: [
        { label: 'Volatility Skew', glyph: 'activity', href: '/options/volatility-skew' },
        { label: 'IV/HV/IVP Chart', glyph: 'trend', href: '/options/iv-hv-ivp' },
        { label: 'IV - HV', glyph: 'percent', href: '/options/iv-hv' },
        { label: 'IV Grid', glyph: 'grid', href: '/options/iv-grid' },
        { label: 'IV - Intraday', glyph: 'sigma', href: '/options/iv-intraday' }
      ]
    },
    {
      title: 'Screeners',
      items: [
        { label: 'OI Crossover', glyph: 'crossover', href: '/options/oi-crossover' },
        { label: 'Intraday Booster', glyph: 'eye', href: '/options/intraday-booster' },
        { label: 'Option Triggers', glyph: 'alert', href: '/options/option-triggers' }
      ]
    }
  ];

  function isActive(href: string): boolean {
    return page.url.pathname === href;
  }
</script>

<div class="mega">
  <div class="mega-head">
    <p class="mega-title">Options Lab</p>
    <p class="mega-sub">Advanced analytics toolkit · All modules coming soon</p>
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
              </a>
            </li>
          {/each}
        </ul>
      </div>
    {/each}
  </div>
</div>

<style>
  .mega {
    position: absolute;
    left: 0;
    top: calc(100% + 0.5rem);
    z-index: var(--mc-z-dropdown);
    width: min(72rem, calc(100vw - 2rem));
    padding: var(--mc-space-5) var(--mc-space-6) var(--mc-space-6);
    border: 1px solid var(--mc-border);
    border-radius: var(--mc-radius-lg);
    background: var(--mc-surface);
    box-shadow: var(--mc-shadow-lg, var(--mc-shadow));
  }

  .mega-head {
    padding-bottom: var(--mc-space-4);
    margin-bottom: var(--mc-space-4);
    border-bottom: 1px solid var(--mc-border);
  }

  .mega-title {
    margin: 0;
    font-size: var(--mc-text-xs);
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--mc-text-subtle);
  }

  .mega-sub {
    margin: 0.3125rem 0 0;
    font-size: var(--mc-text-sm);
    color: var(--mc-text-muted);
  }

  .cols {
    display: grid;
    grid-template-columns: repeat(5, minmax(0, 1fr));
    gap: var(--mc-space-6);
  }

  .col {
    min-width: 0;
  }

  .col + .col {
    padding-left: var(--mc-space-6);
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
    font-size: var(--mc-text-base);
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
    width: 1.375rem;
    height: 1.375rem;
    flex: none;
    color: var(--mc-text-muted);
  }

  .item:hover .ico,
  .item.active .ico {
    color: var(--mc-accent);
  }

  .label {
    min-width: 0;
  }

  @media (max-width: 72rem) {
    .cols {
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: var(--mc-space-4) var(--mc-space-5);
    }

    /* Reset the vertical dividers when the grid wraps to multiple rows. */
    .col + .col {
      padding-left: 0;
      border-left: none;
    }
  }
</style>
