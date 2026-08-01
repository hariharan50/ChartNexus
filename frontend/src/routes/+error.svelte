<script lang="ts">
  import { page } from '$app/state';

  const status = $derived(page.status);
  const detail = $derived(page.error?.detail ?? page.error?.message ?? 'Something went wrong.');
  const requestId = $derived(page.error?.requestId);
</script>

<svelte:head>
  <title>{status} · MarketCompass</title>
</svelte:head>

<section>
  <p class="status mc-numeric">{status}</p>
  <h1>{status === 404 ? 'Page not found' : 'Something went wrong'}</h1>
  <p class="detail">{detail}</p>

  {#if requestId}
    <p class="request-id">
      Reference <code class="mc-numeric">{requestId}</code>
    </p>
  {/if}

  <a href="/dashboard">Back to dashboard</a>
</section>

<style>
  section {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: var(--mc-space-3);
    min-height: 70vh;
    padding: var(--mc-space-8);
    text-align: center;
  }

  .status {
    margin: 0;
    font-size: var(--mc-text-2xl);
    color: var(--mc-text-subtle);
  }

  h1 {
    margin: 0;
    font-size: var(--mc-text-xl);
    font-weight: 600;
  }

  .detail {
    margin: 0;
    max-width: 48ch;
    color: var(--mc-text-muted);
  }

  .request-id {
    margin: 0;
    font-size: var(--mc-text-xs);
    color: var(--mc-text-subtle);
  }
</style>
