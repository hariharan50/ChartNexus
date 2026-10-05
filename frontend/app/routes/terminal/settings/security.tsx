import { useCallback, useEffect, useState } from 'react';
import * as identityApi from '$contexts/identity/api';
import { presentAuthError } from '$contexts/identity/messages';
import type { SessionSummary } from '$contexts/identity/types';
import { useUser } from '$contexts/identity/use-session';
import Button from '$shared/ui/Button';
import { cx } from '$shared/ui/cx';
import IconAlert from '$shared/ui/icons/IconAlert';
import s from './security.module.css';
import type { Route } from './+types/security';

export const meta: Route.MetaFunction = () => [{ title: 'Security · Settings · ChartNexus' }];

type AuthError = ReturnType<typeof presentAuthError>;

export default function SettingsSecurity() {
  const user = useUser();

  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<AuthError | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setSessions(await identityApi.listSessions());
    } catch (caught) {
      setError(presentAuthError(caught));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function signOutEverywhere() {
    setBusy(true);
    setError(null);
    try {
      await identityApi.logoutEverywhere();
      await load();
    } catch (caught) {
      setError(presentAuthError(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <h1 className={s.heading}>Security</h1>

      {error ? (
        <div className={cx(s.banner, s.error)} role="alert">
          <span aria-hidden="true">
            <IconAlert />
          </span>
          <p>{error.message}</p>
        </div>
      ) : null}

      <div className={cx(s.row, s.first)}>
        <div className={s.copy}>
          <p className={s.label}>Email &amp; password</p>
          <p className={s.hint}>Set a unique password to protect your account.</p>
        </div>
        <span className={s.value}>
          {user?.has_password ? 'Enabled' : 'Not set — sign in with Google'}
        </span>
      </div>

      <div className={s.row}>
        <div className={s.copy}>
          <p className={s.label}>Google</p>
          <p className={s.hint}>Sign in with your Google account instead of a password.</p>
        </div>
        <span className={s.value}>
          {user?.linked_providers?.includes('google') ? 'Linked' : 'Not linked'}
        </span>
      </div>

      <div className={s.row}>
        <div className={s.copy}>
          <p className={s.label}>Active sessions</p>
          <p className={s.hint}>Devices currently signed in to your account.</p>
        </div>
        <Button variant="secondary" onClick={signOutEverywhere} loading={busy}>
          Sign out everywhere
        </Button>
      </div>

      {loading ? (
        <p className={cx(s.hint, s.indent)}>Loading…</p>
      ) : sessions.length === 0 ? (
        <p className={cx(s.hint, s.indent)}>No active sessions.</p>
      ) : (
        sessions.map((item) => (
          <div className={s.session} key={item.id}>
            <div className={s.copy}>
              <p className={cx(s.label, s.sm)}>
                {describe(item)}
                {item.is_current ? <span className={s.badge}>This device</span> : null}
              </p>
              <p className={s.hint}>
                {item.ip_address || 'Unknown IP'} · signed in{' '}
                {new Date(item.created_at).toLocaleString()}
              </p>
            </div>
          </div>
        ))
      )}
    </>
  );
}

function describe(item: SessionSummary): string {
  if (!item.user_agent) return 'Unknown device';
  if (/mobile/i.test(item.user_agent)) return 'Mobile browser';
  if (/chrome/i.test(item.user_agent)) return 'Chrome';
  if (/firefox/i.test(item.user_agent)) return 'Firefox';
  if (/safari/i.test(item.user_agent)) return 'Safari';
  if (/edg/i.test(item.user_agent)) return 'Edge';
  return 'Browser session';
}
