import { useEffect, useRef, useState } from 'react';
import { useNavigate, useRevalidator, useSearchParams } from 'react-router';
import * as broker from '$contexts/broker-connections/api';
import { presentAuthError } from '$contexts/identity/messages';
import Button from '$shared/ui/Button';
import IconAlert from '$shared/ui/icons/IconAlert';
import s from './callback.module.css';
import type { Route } from './+types/callback';

/**
 * Where FYERS returns the user (MC_BROKER_FYERS_REDIRECT_URI).
 *
 * The auth code lands in the address bar, so it is handed to the API
 * immediately and the history entry is replaced — a code left in history can
 * be replayed from the back button or leaked in a referrer.
 */

export const meta: Route.MetaFunction = () => [
  { title: 'Connecting broker · MarketCompass' },
  { name: 'robots', content: 'noindex' }
];

type AuthError = ReturnType<typeof presentAuthError>;

export default function BrokerCallback() {
  const navigate = useNavigate();
  const revalidator = useRevalidator();
  const [searchParams] = useSearchParams();
  const [error, setError] = useState<AuthError | null>(null);

  // An authorization code can be exchanged exactly once; React runs effects
  // twice under StrictMode in development. Latch rather than rely on deps.
  const exchanged = useRef(false);

  useEffect(() => {
    if (exchanged.current) return;
    exchanged.current = true;

    async function complete() {
      if (searchParams.get('error')) {
        setError({ message: 'The broker cancelled this connection.' });
        return;
      }

      // FYERS uses `auth_code`; `code` is accepted as a fallback.
      const code = searchParams.get('auth_code') ?? searchParams.get('code');
      const state = searchParams.get('state');
      if (!code || !state) {
        setError({ message: 'This connection link is incomplete. Start again.' });
        return;
      }

      try {
        await broker.completeConnect(code, state);
        await navigate('/settings/broker?connected=1', { replace: true });
        // `invalidateAll` — the connection state the terminal loader saw is stale.
        void revalidator.revalidate();
      } catch (caught) {
        setError(presentAuthError(caught));
      }
    }

    void complete();
  }, [navigate, revalidator, searchParams]);

  return (
    <div className={s.state}>
      {error ? (
        <>
          <span className={s.icon} aria-hidden="true">
            <IconAlert />
          </span>
          <h1>Connection failed</h1>
          <p>{error.message}</p>
          <Button
            variant="secondary"
            onClick={() => void navigate('/settings/broker', { replace: true })}
          >
            Back to broker settings
          </Button>
        </>
      ) : (
        <>
          <span className={s.spinner} aria-hidden="true" />
          <h1>Connecting your broker…</h1>
          <p>Exchanging the authorisation code.</p>
        </>
      )}
    </div>
  );
}
