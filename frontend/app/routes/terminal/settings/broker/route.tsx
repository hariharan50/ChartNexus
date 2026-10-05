import { useCallback, useEffect, useState, type FormEvent } from 'react';
import * as broker from '$contexts/broker-connections/api';
import type { BrokerConnection } from '$contexts/broker-connections/types';
import { presentAuthError } from '$contexts/identity/messages';
import Button from '$shared/ui/Button';
import { cx } from '$shared/ui/cx';
import IconAlert from '$shared/ui/icons/IconAlert';
import IconCheck from '$shared/ui/icons/IconCheck';
import PasswordField from '$shared/ui/PasswordField';
import TextField from '$shared/ui/TextField';
import s from './route.module.css';
import type { Route } from './+types/route';

export const meta: Route.MetaFunction = () => [{ title: 'Broker · ChartNexus' }];

type AuthError = ReturnType<typeof presentAuthError>;
type Busy = 'save' | 'connect' | 'disconnect' | 'revoke' | null;

export default function SettingsBroker() {
  const [connection, setConnection] = useState<BrokerConnection | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<Busy>(null);
  const [error, setError] = useState<AuthError | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const [appId, setAppId] = useState('');
  const [secretId, setSecretId] = useState('');

  const status = connection?.status ?? 'pending';
  const canConnect = !!connection?.configured;

  const headline = !connection?.configured
    ? 'Not set up'
    : connection.connected
      ? `Connected as ${connection.display_name || 'your account'}`
      : status === 'expired'
        ? 'Session expired'
        : 'Ready to connect';

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setConnection(await broker.getConnection());
    } catch (caught) {
      setError(presentAuthError(caught));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function run<T>(kind: Busy, action: () => Promise<T>): Promise<T | undefined> {
    setBusy(kind);
    setError(null);
    setNotice(null);
    try {
      return await action();
    } catch (caught) {
      setError(presentAuthError(caught));
      return undefined;
    } finally {
      setBusy(null);
    }
  }

  async function saveCredentials(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const result = await run('save', () => broker.saveCredentials(appId.trim(), secretId));
    if (result) {
      setConnection(result);
      // The secret is write-only from here on: the API will never return it.
      setSecretId('');
      setNotice('Credentials saved. You can connect now.');
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
      setConnection(result);
      setNotice('Disconnected. Your API credentials are still saved.');
    }
  }

  async function revoke() {
    const result = await run('revoke', () => broker.revokeCredentials());
    if (result) {
      setConnection(result);
      setAppId('');
      setNotice('Credentials removed.');
    }
  }

  return (
    <section className={s.page}>
      <header>
        <h1>Broker connection</h1>
        <p>
          Connect your FYERS account to replace simulated data with live NIFTY, BANKNIFTY and SENSEX
          prices.
        </p>
      </header>

      {error ? (
        <div className={cx(s.banner, s.error)} role="alert">
          <span aria-hidden="true">
            <IconAlert />
          </span>
          <p>{error.message}</p>
        </div>
      ) : null}

      {notice ? (
        <div className={cx(s.banner, s.ok)} role="status">
          <span aria-hidden="true">
            <IconCheck />
          </span>
          <p>{notice}</p>
        </div>
      ) : null}

      <article className={cx(s.card, s.statusCard)}>
        <div className={s.statusHead}>
          <span className={cx(s.pill, s[status])}>{status}</span>
          <strong>{loading ? 'Checking…' : headline}</strong>
        </div>

        {connection?.configured ? (
          <dl>
            <div>
              <dt>App ID</dt>
              <dd className="cn-numeric">{connection.masked_app_id}</dd>
            </div>
            {connection.broker_user_id ? (
              <div>
                <dt>Broker ID</dt>
                <dd className="cn-numeric">{connection.broker_user_id}</dd>
              </div>
            ) : null}
            {connection.last_validated_at ? (
              <div>
                <dt>Last checked</dt>
                <dd>{new Date(connection.last_validated_at).toLocaleString()}</dd>
              </div>
            ) : null}
          </dl>
        ) : null}

        {connection?.last_error ? (
          <p className={s.lastError}>Broker said: {connection.last_error}</p>
        ) : null}

        <div className={s.actions}>
          <Button onClick={connect} loading={busy === 'connect'} disabled={!canConnect}>
            {connection?.connected ? 'Reconnect' : 'Connect with FYERS'}
          </Button>
          {connection?.connected ? (
            <Button variant="secondary" onClick={disconnect} loading={busy === 'disconnect'}>
              Disconnect
            </Button>
          ) : null}
          {connection?.configured ? (
            <Button variant="ghost" onClick={revoke} loading={busy === 'revoke'}>
              Remove credentials
            </Button>
          ) : null}
        </div>
      </article>

      <article className={s.card}>
        <h2>API credentials</h2>
        <ol className={s.steps}>
          <li>
            Create an app at{' '}
            <a href="https://myapi.fyers.in/dashboard" target="_blank" rel="noreferrer noopener">
              myapi.fyers.in
            </a>
          </li>
          <li>
            Set its redirect URI to exactly{' '}
            <code className="cn-numeric">{connection?.redirect_uri ?? '—'}</code>
          </li>
          <li>Paste the App ID and Secret ID below</li>
        </ol>

        <form className={s.form} onSubmit={saveCredentials}>
          <TextField
            className={s.formField}
            label="App ID"
            value={appId}
            onValueChange={setAppId}
            placeholder="ABCDE123XY-100"
            autoComplete="off"
            required
          />
          <PasswordField
            className={s.formField}
            label="Secret ID"
            value={secretId}
            onValueChange={setSecretId}
            placeholder="Your app secret"
            autocomplete="new-password"
            required
          />
          <p className={s.hint}>
            Stored encrypted. It is never shown again and never sent to your browser.
          </p>
          <Button type="submit" loading={busy === 'save'}>
            {connection?.configured ? 'Replace credentials' : 'Save credentials'}
          </Button>
        </form>
      </article>
    </section>
  );
}
