<script lang="ts">
  import * as broker from '$contexts/broker-connections/api';
  import type { BrokerConnection } from '$contexts/broker-connections/types';
  import { presentAuthError } from '$contexts/identity/messages';
  import Button from '$shared/ui/Button.svelte';
  import PasswordField from '$shared/ui/PasswordField.svelte';
  import TextField from '$shared/ui/TextField.svelte';
  import IconAlert from '$shared/ui/icons/IconAlert.svelte';
  import IconCheck from '$shared/ui/icons/IconCheck.svelte';

  let connection = $state<BrokerConnection | null>(null);
  let loading = $state(true);
  let busy = $state<'save' | 'connect' | 'disconnect' | 'revoke' | null>(null);
  let error = $state<ReturnType<typeof presentAuthError> | null>(null);
  let notice = $state<string | null>(null);

  let appId = $state('');
  let secretId = $state('');

  const status = $derived(connection?.status ?? 'pending');
  const canConnect = $derived(!!connection?.configured);

  const headline = $derived.by(() => {
    if (!connection?.configured) return 'Not set up';
    if (connection.connected) return `Connected as ${connection.display_name || 'your account'}`;
    if (status === 'expired') return 'Session expired';
    return 'Ready to connect';
  });

  $effect(() => {
    void load();
  });

  async function load() {
    loading = true;
    try {
      connection = await broker.getConnection();
    } catch (caught) {
      error = presentAuthError(caught);
    } finally {
      loading = false;
    }
  }

  async function run<T>(kind: typeof busy, action: () => Promise<T>): Promise<T | undefined> {
    busy = kind;
    error = null;
    notice = null;
    try {
      return await action();
    } catch (caught) {
      error = presentAuthError(caught);
      return undefined;
    } finally {
      busy = null;
    }
  }

  async function saveCredentials(event: SubmitEvent) {
    event.preventDefault();
    const result = await run('save', () => broker.saveCredentials(appId.trim(), secretId));
    if (result) {
      connection = result;
      // The secret is write-only from here on: the API will never return it.
      secretId = '';
      notice = 'Credentials saved. You can connect now.';
    }
  }

  async function connect() {
    const result = await run('connect', () => broker.startConnect('/settings/broker'));
    if (result) {
      // Full navigation: the next stop is the broker's own origin.
      window.location.assign(result.authorization_url);
    }
  }

  async function disconnect() {
    const result = await run('disconnect', () => broker.disconnect());
    if (result) {
      connection = result;
      notice = 'Disconnected. Your API credentials are still saved.';
    }
  }

  async function revoke() {
    const result = await run('revoke', () => broker.revokeCredentials());
    if (result) {
      connection = result;
      appId = '';
      notice = 'Credentials removed.';
    }
  }
</script>

<svelte:head>
  <title>Broker · MarketCompass</title>
</svelte:head>

<section>
  <header>
    <h1>Broker connection</h1>
    <p>
      Connect your FYERS account to replace simulated data with live NIFTY, BANKNIFTY and SENSEX
      prices.
    </p>
  </header>

  {#if error}
    <div class="banner error" role="alert">
      <span aria-hidden="true"><IconAlert /></span>
      <p>{error.message}</p>
    </div>
  {/if}

  {#if notice}
    <div class="banner ok" role="status">
      <span aria-hidden="true"><IconCheck /></span>
      <p>{notice}</p>
    </div>
  {/if}

  <article class="card status-card">
    <div class="status-head">
      <span class="pill {status}">{status}</span>
      <strong>{loading ? 'Checking…' : headline}</strong>
    </div>

    {#if connection?.configured}
      <dl>
        <div>
          <dt>App ID</dt>
          <dd class="mc-numeric">{connection.masked_app_id}</dd>
        </div>
        {#if connection.broker_user_id}
          <div>
            <dt>Broker ID</dt>
            <dd class="mc-numeric">{connection.broker_user_id}</dd>
          </div>
        {/if}
        {#if connection.last_validated_at}
          <div>
            <dt>Last checked</dt>
            <dd>{new Date(connection.last_validated_at).toLocaleString()}</dd>
          </div>
        {/if}
      </dl>
    {/if}

    {#if connection?.last_error}
      <p class="last-error">Broker said: {connection.last_error}</p>
    {/if}

    <div class="actions">
      <Button onclick={connect} loading={busy === 'connect'} disabled={!canConnect}>
        {connection?.connected ? 'Reconnect' : 'Connect with FYERS'}
      </Button>
      {#if connection?.connected}
        <Button variant="secondary" onclick={disconnect} loading={busy === 'disconnect'}>
          Disconnect
        </Button>
      {/if}
      {#if connection?.configured}
        <Button variant="ghost" onclick={revoke} loading={busy === 'revoke'}>
          Remove credentials
        </Button>
      {/if}
    </div>
  </article>

  <article class="card">
    <h2>API credentials</h2>
    <ol class="steps">
      <li>
        Create an app at
        <a href="https://myapi.fyers.in/dashboard" target="_blank" rel="noreferrer noopener">
          myapi.fyers.in
        </a>
      </li>
      <li>
        Set its redirect URI to exactly
        <code class="mc-numeric">{connection?.redirect_uri ?? '—'}</code>
      </li>
      <li>Paste the App ID and Secret ID below</li>
    </ol>

    <form onsubmit={saveCredentials}>
      <TextField
        label="App ID"
        bind:value={appId}
        placeholder="ABCDE123XY-100"
        autocomplete="off"
        required
      />
      <PasswordField
        label="Secret ID"
        bind:value={secretId}
        placeholder="Your app secret"
        autocomplete="new-password"
        required
      />
      <p class="hint">Stored encrypted. It is never shown again and never sent to your browser.</p>
      <Button type="submit" loading={busy === 'save'}>
        {connection?.configured ? 'Replace credentials' : 'Save credentials'}
      </Button>
    </form>
  </article>
</section>

<style>
  section {
    max-width: 44rem;
    display: flex;
    flex-direction: column;
    gap: var(--mc-space-4);
  }

  h1 {
    margin: 0 0 0.25rem;
    font-size: var(--mc-text-xl);
    font-weight: 700;
    letter-spacing: -0.01em;
  }

  header p {
    margin: 0;
    font-size: var(--mc-text-sm);
    color: var(--mc-text-muted);
  }

  h2 {
    margin: 0 0 var(--mc-space-3);
    font-size: var(--mc-text-base);
    font-weight: 600;
  }

  .card {
    padding: var(--mc-space-4);
    border: 1px solid var(--mc-border);
    border-radius: var(--mc-radius);
    background: var(--mc-surface);
  }

  .status-head {
    display: flex;
    align-items: center;
    gap: var(--mc-space-3);
    font-size: var(--mc-text-sm);
  }

  .pill {
    padding: 0.125rem 0.5rem;
    border-radius: 999px;
    border: 1px solid var(--mc-border-strong);
    font-size: var(--mc-text-xs);
    font-weight: 600;
    text-transform: capitalize;
    color: var(--mc-text-muted);
  }

  .pill.active {
    color: var(--mc-live);
    border-color: color-mix(in srgb, var(--mc-live) 40%, transparent);
    background: color-mix(in srgb, var(--mc-live) 12%, transparent);
  }

  .pill.expired {
    color: var(--mc-warning);
    border-color: color-mix(in srgb, var(--mc-warning) 40%, transparent);
    background: color-mix(in srgb, var(--mc-warning) 12%, transparent);
  }

  dl {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(9rem, 1fr));
    gap: var(--mc-space-3);
    margin: var(--mc-space-4) 0 0;
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
  }

  .last-error {
    margin: var(--mc-space-3) 0 0;
    font-size: var(--mc-text-xs);
    color: var(--mc-warning);
  }

  .actions {
    display: flex;
    flex-wrap: wrap;
    gap: var(--mc-space-2);
    margin-top: var(--mc-space-4);
  }

  .steps {
    margin: 0 0 var(--mc-space-4);
    padding-left: 1.125rem;
    font-size: var(--mc-text-sm);
    line-height: 1.7;
    color: var(--mc-text-muted);
  }

  code {
    padding: 0.0625rem 0.3125rem;
    border-radius: var(--mc-radius-sm);
    background: var(--mc-field-bg);
    font-size: var(--mc-text-xs);
  }

  form {
    display: flex;
    flex-direction: column;
    gap: 0.875rem;
    align-items: flex-start;
  }

  form :global(.field) {
    width: 100%;
  }

  .hint {
    margin: 0;
    font-size: var(--mc-text-xs);
    color: var(--mc-text-subtle);
  }

  .banner {
    display: flex;
    align-items: center;
    gap: var(--mc-space-2);
    padding: 0.625rem 0.75rem;
    border-radius: var(--mc-radius);
    font-size: var(--mc-text-sm);
  }

  .banner p {
    margin: 0;
  }

  .banner.error {
    border: 1px solid color-mix(in srgb, var(--mc-danger) 40%, transparent);
    background: color-mix(in srgb, var(--mc-danger) 12%, transparent);
    color: var(--mc-text);
  }

  .banner.error span {
    color: var(--mc-danger);
  }

  .banner.ok {
    border: 1px solid color-mix(in srgb, var(--mc-live) 40%, transparent);
    background: color-mix(in srgb, var(--mc-live) 12%, transparent);
  }

  .banner.ok span {
    color: var(--mc-live);
  }
</style>
