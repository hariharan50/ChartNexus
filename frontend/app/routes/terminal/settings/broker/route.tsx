import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { useSearchParams } from 'react-router';
import * as broker from '$contexts/broker-connections/api';
import type {
  BrokerConnection,
  BrokerConnections,
  BrokerName
} from '$contexts/broker-connections/types';
import { presentAuthError } from '$contexts/identity/messages';
import Button from '$shared/ui/Button';
import { cx } from '$shared/ui/cx';
import IconAlert from '$shared/ui/icons/IconAlert';
import IconArrowLeft from '$shared/ui/icons/IconArrowLeft';
import IconCheck from '$shared/ui/icons/IconCheck';
import PasswordField from '$shared/ui/PasswordField';
import TextField from '$shared/ui/TextField';
import s from './route.module.css';
import MyBrokerUsage from './MyBrokerUsage';
import type { Route } from './+types/route';

export const meta: Route.MetaFunction = () => [{ title: 'Broker · ChartNexus' }];

type AuthError = ReturnType<typeof presentAuthError>;
type Busy = 'save' | 'connect' | 'disconnect' | 'revoke' | null;

/** What differs between the brokers on this page. Everything else is shared. */
interface BrokerCopy {
  name: string;
  tagline: string;
  consoleUrl: string;
  consoleLabel: string;
  appIdLabel: string;
  appIdPlaceholder: string;
  secretLabel: string;
  /** Kite only: the optional login ID that pins the connection to one account. */
  clientIdLabel?: string;
  /** Shown once connected, so the daily re-login is not a surprise. */
  sessionNote: string;
}

const COPY: Record<BrokerName, BrokerCopy> = {
  kite: {
    name: 'Zerodha Kite',
    tagline: 'Kite Connect · quotes, F&O, option chains, live ticks',
    consoleUrl: 'https://developers.kite.trade/apps',
    consoleLabel: 'developers.kite.trade',
    appIdLabel: 'API key',
    appIdPlaceholder: 'Your Kite API key',
    secretLabel: 'API secret',
    clientIdLabel: 'Zerodha Client ID (optional)',
    sessionNote: 'Zerodha ends every session at 6:00 AM IST — reconnect each trading day.'
  },
  fyers: {
    name: 'FYERS',
    tagline: 'FYERS API v3 · quotes, F&O, option chains, live ticks',
    consoleUrl: 'https://myapi.fyers.in/dashboard',
    consoleLabel: 'myapi.fyers.in',
    appIdLabel: 'App ID',
    appIdPlaceholder: 'ABCDE123XY-100',
    secretLabel: 'Secret ID',
    sessionNote: 'FYERS tokens expire daily — reconnect when the status says so.'
  }
};

const ORDER: readonly BrokerName[] = ['kite', 'fyers'];

/** The broker's own logo, served from `public/brokers/`. Decorative: the name sits beside it. */
function BrokerMark({ name }: { name: BrokerName }) {
  return (
    <span className={cx(s.mark, s[name])} aria-hidden="true">
      <img className={s.markLogo} src={`/brokers/${name}.png`} alt="" width={44} height={44} />
    </span>
  );
}

function isBroker(value: string | null): value is BrokerName {
  return value === 'kite' || value === 'fyers';
}

/** One short phrase for a connection's state, used on the tile and the detail head. */
function headline(connection: BrokerConnection | null): string {
  if (!connection?.configured) return 'Not set up';
  if (connection.connected) return `Connected as ${connection.display_name || 'your account'}`;
  if (connection.status === 'expired') return 'Session expired';
  return 'Ready to connect';
}

export default function SettingsBroker() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [data, setData] = useState<BrokerConnections | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<AuthError | null>(null);

  const requested = searchParams.get('broker');
  const selected = isBroker(requested) ? requested : null;
  const justConnected = searchParams.get('connected') !== null;

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setData(await broker.listConnections());
    } catch (caught) {
      setError(presentAuthError(caught));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const byName = new Map(data?.connections.map((row) => [row.broker, row]) ?? []);

  function open(name: BrokerName) {
    // A history entry, so the browser's back button returns to the picker too.
    setSearchParams({ broker: name });
  }

  function back() {
    setSearchParams({});
  }

  return (
    <section className={s.page}>
      <header className={s.header}>
        <h1>{selected ? 'Broker connection' : 'Broker integration'}</h1>
        <p>
          {selected
            ? `Manage your ${COPY[selected].name} keys and session.`
            : 'Choose the broker that streams live NIFTY, BANKNIFTY and SENSEX data into ChartNexus.'}
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

      {selected ? (
        <BrokerDetail
          key={selected}
          name={selected}
          connection={byName.get(selected) ?? null}
          active={data?.active_broker === selected}
          loading={loading}
          justConnected={justConnected}
          onBack={back}
          // Connecting or disconnecting one broker can change the other.
          onChanged={load}
        />
      ) : (
        <>
          <div className={s.picker} role="list" aria-label="Brokers">
            {ORDER.map((name) => (
              <BrokerTile
                key={name}
                name={name}
                connection={byName.get(name) ?? null}
                active={data?.active_broker === name}
                loading={loading}
                onOpen={() => open(name)}
              />
            ))}
          </div>
          <p className={s.note}>
            Only one broker can be connected at a time — connecting one disconnects the other. Both
            sets of keys stay saved, so switching back is one click.
          </p>
          <MyBrokerUsage />
        </>
      )}
    </section>
  );
}

// -- step 1: the picker --------------------------------------------------------

interface BrokerTileProps {
  name: BrokerName;
  connection: BrokerConnection | null;
  active: boolean;
  loading: boolean;
  onOpen: () => void;
}

function BrokerTile({ name, connection, active, loading, onOpen }: BrokerTileProps) {
  const copy = COPY[name];
  const status = connection?.status ?? 'pending';

  return (
    <div role="listitem">
      <button
        type="button"
        className={cx(s.tile, active && s.tileActive)}
        onClick={onOpen}
        aria-label={`${copy.name}: ${loading ? 'checking' : headline(connection)}. Open settings`}
      >
        <BrokerMark name={name} />
        <span className={s.tileBody}>
          <span className={s.tileName}>
            {copy.name}
            {active ? <span className={cx(s.pill, s.active)}>In use</span> : null}
          </span>
          <span className={s.tileTagline}>{copy.tagline}</span>
          <span className={s.tileStatus}>
            <span className={cx(s.dot, s[status], !connection?.configured && s.unset)} />
            {loading ? 'Checking…' : headline(connection)}
          </span>
        </span>
        <span className={s.chevron} aria-hidden="true">
          <IconArrowLeft />
        </span>
      </button>
    </div>
  );
}

// -- step 2: one broker's connection ------------------------------------------

interface BrokerDetailProps {
  name: BrokerName;
  connection: BrokerConnection | null;
  active: boolean;
  loading: boolean;
  justConnected: boolean;
  onBack: () => void;
  onChanged: () => Promise<void>;
}

function BrokerDetail({
  name,
  connection,
  active,
  loading,
  justConnected,
  onBack,
  onChanged
}: BrokerDetailProps) {
  const copy = COPY[name];
  const [busy, setBusy] = useState<Busy>(null);
  const [error, setError] = useState<AuthError | null>(null);
  const [notice, setNotice] = useState<string | null>(
    justConnected ? `${copy.name} connected. Live data is on its way.` : null
  );

  const [appId, setAppId] = useState('');
  const [secretId, setSecretId] = useState('');
  const [clientId, setClientId] = useState('');

  const status = connection?.status ?? 'pending';
  const canConnect = !!connection?.configured;

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
    const result = await run('save', () =>
      broker.saveCredentials(appId.trim(), secretId.trim(), name, clientId.trim() || undefined)
    );
    if (result) {
      // The secret is write-only from here on: the API will never return it.
      setSecretId('');
      setNotice('Credentials saved. You can connect now.');
      await onChanged();
    }
  }

  async function connect() {
    const result = await run('connect', () =>
      broker.startConnect(`/settings/broker?broker=${name}`, name)
    );
    if (result) {
      // Full navigation: the next stop is the broker's own origin.
      window.location.assign(result.authorization_url);
    }
  }

  async function disconnect() {
    const result = await run('disconnect', () => broker.disconnect(name));
    if (result) {
      setNotice('Disconnected. Your API credentials are still saved.');
      await onChanged();
    }
  }

  async function revoke() {
    const result = await run('revoke', () => broker.revokeCredentials(name));
    if (result) {
      setAppId('');
      setClientId('');
      setNotice('Credentials removed.');
      await onChanged();
    }
  }

  return (
    <div className={s.detail}>
      <button type="button" className={s.back} onClick={onBack}>
        <IconArrowLeft />
        All brokers
      </button>

      <div className={s.detailHead}>
        <BrokerMark name={name} />
        <div>
          <h2>
            {copy.name}
            {active ? <span className={cx(s.pill, s.active)}>In use</span> : null}
          </h2>
          <p>{copy.tagline}</p>
        </div>
      </div>

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

      <article className={s.card} aria-labelledby={`${name}-connection`}>
        <h3 id={`${name}-connection`}>Connection</h3>
        <div className={s.statusHead}>
          {connection?.configured ? <span className={cx(s.pill, s[status])}>{status}</span> : null}
          <strong>{loading ? 'Checking…' : headline(connection)}</strong>
        </div>

        {connection?.configured ? (
          <dl>
            <div>
              <dt>{copy.appIdLabel}</dt>
              <dd className="cn-numeric">{connection.masked_app_id}</dd>
            </div>
            {connection.broker_user_id ? (
              <div>
                <dt>Broker ID</dt>
                <dd className="cn-numeric">{connection.broker_user_id}</dd>
              </div>
            ) : connection.client_id ? (
              <div>
                <dt>Expected account</dt>
                <dd className="cn-numeric">{connection.client_id}</dd>
              </div>
            ) : null}
            {connection.connected && connection.expires_at ? (
              <div>
                <dt>Valid until</dt>
                <dd>{formatExpiry(connection.expires_at)}</dd>
              </div>
            ) : null}
            {connection.last_validated_at ? (
              <div>
                <dt>Last checked</dt>
                <dd>{new Date(connection.last_validated_at).toLocaleString()}</dd>
              </div>
            ) : null}
          </dl>
        ) : (
          <p className={s.hint}>Save your API credentials below, then connect.</p>
        )}

        {connection?.last_error ? (
          <p className={s.lastError}>Broker said: {connection.last_error}</p>
        ) : null}

        {connection?.connected ? <p className={s.hint}>{copy.sessionNote}</p> : null}

        <div className={s.actions}>
          <Button onClick={connect} loading={busy === 'connect'} disabled={!canConnect}>
            {connection?.connected ? 'Reconnect' : `Connect with ${copy.name}`}
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

      <article className={s.card} aria-labelledby={`${name}-credentials`}>
        <h3 id={`${name}-credentials`}>API credentials</h3>
        <ol className={s.steps}>
          <li>
            Create an app at{' '}
            <a href={copy.consoleUrl} target="_blank" rel="noreferrer noopener">
              {copy.consoleLabel}
            </a>
          </li>
          <li>
            Set its redirect URL to exactly{' '}
            <code className="cn-numeric">{connection?.redirect_uri ?? '—'}</code>
          </li>
          <li>
            Paste the {copy.appIdLabel} and {copy.secretLabel} below
          </li>
        </ol>

        <form className={s.form} onSubmit={saveCredentials}>
          <TextField
            className={s.formField}
            label={copy.appIdLabel}
            value={appId}
            onValueChange={setAppId}
            placeholder={copy.appIdPlaceholder}
            autoComplete="off"
            required
          />
          <PasswordField
            className={s.formField}
            label={copy.secretLabel}
            value={secretId}
            onValueChange={setSecretId}
            placeholder="Your app secret"
            autocomplete="new-password"
            required
          />
          {copy.clientIdLabel ? (
            <TextField
              className={s.formField}
              label={copy.clientIdLabel}
              value={clientId}
              onValueChange={setClientId}
              placeholder="AB1234"
              autoComplete="off"
            />
          ) : null}
          <p className={s.hint}>
            Stored encrypted. It is never shown again and never sent to your browser.
            {copy.clientIdLabel
              ? ' With a Client ID, a login as any other Zerodha account is refused.'
              : ''}
          </p>
          <Button type="submit" loading={busy === 'save'}>
            {connection?.configured ? 'Replace credentials' : 'Save credentials'}
          </Button>
        </form>
      </article>
    </div>
  );
}

/** "6:00 AM, 4 Aug" in the viewer's locale — the moment the broker logs out. */
function formatExpiry(iso: string): string {
  const moment = new Date(iso);
  if (Number.isNaN(moment.getTime())) return '—';
  return moment.toLocaleString(undefined, {
    hour: 'numeric',
    minute: '2-digit',
    day: 'numeric',
    month: 'short'
  });
}
