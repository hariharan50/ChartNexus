<script lang="ts">
  import IconBolt from '$shared/ui/icons/IconBolt.svelte';
  import IconChart from '$shared/ui/icons/IconChart.svelte';
  import IconBrain from '$shared/ui/icons/IconBrain.svelte';
  import IconBank from '$shared/ui/icons/IconBank.svelte';

  let { children } = $props();

  const features = [
    {
      icon: IconChart,
      title: 'Options Intelligence',
      body: 'Live chain analytics, PCR, max pain and OI build-up across NIFTY & SENSEX.'
    },
    {
      icon: IconBrain,
      title: 'AI Signal Engine',
      body: 'Model-driven bias, regime detection and illustrative risk frameworks.'
    },
    {
      icon: IconBank,
      title: 'Institutional Flow',
      body: 'Track FII/DII positioning and smart-money footprints in real time.'
    }
  ];
</script>

<div class="auth-layout">
  <!-- Decorative on small screens the panel is hidden entirely, so nothing
       here may carry information the form needs. -->
  <aside class="brand-panel">
    <div class="brand-inner">
      <div class="wordmark">
        <span class="mark" aria-hidden="true"><IconBolt /></span>
        <span class="name">MarketCompass</span>
      </div>

      <div class="pitch">
        <h1>Analyse Markets.<br />Trade Smarter.</h1>
        <p>
          An AI trading-intelligence terminal for NIFTY 50 and SENSEX — options analytics, market
          regimes and institutional flow in one place.
        </p>
      </div>

      <ul class="features">
        {#each features as feature (feature.title)}
          {@const Icon = feature.icon}
          <li>
            <span class="feature-icon" aria-hidden="true"><Icon /></span>
            <div>
              <p class="feature-title">{feature.title}</p>
              <p class="feature-body">{feature.body}</p>
            </div>
          </li>
        {/each}
      </ul>

      <p class="disclaimer">For educational purposes only · Not investment advice</p>
    </div>
  </aside>

  <main class="form-panel">
    <div class="form-inner">
      {@render children()}
    </div>
  </main>
</div>

<style>
  .auth-layout {
    display: grid;
    grid-template-columns: 1fr 1fr;
    min-height: 100vh;
    min-height: 100dvh;
    background: var(--mc-auth-bg);
  }

  /* --- left panel --------------------------------------------------------- */

  .brand-panel {
    position: relative;
    overflow: hidden;
    /* Two layers: a warm radial highlight over a deep rust base, matching the
       terminal's amber accent. */
    background:
      radial-gradient(120% 90% at 15% 0%, #b4441c 0%, transparent 60%),
      linear-gradient(160deg, #a53d18 0%, #5e2310 55%, #2a1008 100%);
    color: #fff;
  }

  /* Faint grid, evoking a chart surface without competing with the text. */
  .brand-panel::before {
    content: '';
    position: absolute;
    inset: 0;
    background-image:
      linear-gradient(rgb(255 255 255 / 0.05) 1px, transparent 1px),
      linear-gradient(90deg, rgb(255 255 255 / 0.05) 1px, transparent 1px);
    background-size: 44px 44px;
    mask-image: radial-gradient(120% 100% at 20% 10%, #000 0%, transparent 75%);
    pointer-events: none;
  }

  .brand-inner {
    position: relative;
    display: flex;
    flex-direction: column;
    gap: var(--mc-space-6);
    height: 100%;
    padding: clamp(1.75rem, 3vw, 2.75rem);
  }

  .wordmark {
    display: flex;
    align-items: center;
    gap: var(--mc-space-3);
  }

  .mark {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 2.125rem;
    height: 2.125rem;
    border-radius: var(--mc-radius);
    background: rgb(255 255 255 / 0.15);
    border: 1px solid rgb(255 255 255 / 0.2);
    color: #fff;
  }

  .name {
    font-size: 1.0625rem;
    font-weight: 700;
    letter-spacing: -0.01em;
  }

  .pitch {
    margin-top: auto;
  }

  h1 {
    margin: 0 0 var(--mc-space-4);
    font-size: clamp(1.625rem, 2.5vw, 2.125rem);
    line-height: 1.15;
    font-weight: 700;
    letter-spacing: -0.02em;
  }

  .pitch p {
    margin: 0;
    max-width: 30rem;
    font-size: var(--mc-text-base);
    line-height: 1.6;
    color: rgb(255 255 255 / 0.78);
  }

  .features {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .features li {
    display: flex;
    align-items: flex-start;
    gap: var(--mc-space-3);
    padding: 0.75rem;
    border: 1px solid rgb(255 255 255 / 0.14);
    border-radius: var(--mc-radius);
    background: rgb(255 255 255 / 0.07);
    backdrop-filter: blur(2px);
  }

  .feature-icon {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    width: 1.75rem;
    height: 1.75rem;
    border-radius: var(--mc-radius-sm);
    background: rgb(0 0 0 / 0.22);
    border: 1px solid rgb(255 255 255 / 0.14);
  }

  .feature-title {
    margin: 0 0 0.125rem;
    font-size: var(--mc-text-base);
    font-weight: 600;
  }

  .feature-body {
    margin: 0;
    font-size: var(--mc-text-xs);
    line-height: 1.45;
    color: rgb(255 255 255 / 0.72);
  }

  .disclaimer {
    margin: 0;
    font-size: var(--mc-text-xs);
    color: rgb(255 255 255 / 0.6);
  }

  /* --- right panel -------------------------------------------------------- */

  .form-panel {
    display: flex;
    align-items: center;
    justify-content: center;
    padding: clamp(1.5rem, 3vw, 2.5rem);
  }

  .form-inner {
    width: 100%;
    max-width: 21rem;
  }

  /* Below this width the two columns each become too narrow to read, so the
     marketing panel drops out entirely rather than being squeezed. */
  @media (max-width: 60rem) {
    .auth-layout {
      grid-template-columns: 1fr;
    }

    .brand-panel {
      display: none;
    }

    .form-panel {
      align-items: flex-start;
      padding-top: clamp(3rem, 12vh, 6rem);
    }
  }
</style>
