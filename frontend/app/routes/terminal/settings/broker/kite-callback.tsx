import { useEffect, useRef, useState } from 'react';
import { useNavigate, useRevalidator, useSearchParams } from 'react-router';
import * as broker from '$contexts/broker-connections/api';
import { presentAuthError } from '$contexts/identity/messages';
import Button from '$shared/ui/Button';
import IconAlert from '$shared/ui/icons/IconAlert';
import s from './callback.module.css';
import type { Route } from './+types/kite-callback';

/**
 * Where Zerodha returns the user (the redirect URL registered on the Kite app,
 * shown in Settings → Broker from CN_KITE_REDIRECT_URI).
 *
 * Kite appends `?action=login&status=success&request_token=…`, plus our
 * `state`, which rode through its `redirect_params` (ADR 0002). The request
 * token is single-use and sits in the address bar, so it is handed to the API
 * at once and the history entry is replaced — exactly as for FYERS.
 */

export const meta: Route.MetaFunction = () => [
  { title: 'Connecting Zerodha · ChartNexus' },
  { name: 'robots', content: 'noindex' }
];

type AuthError = ReturnType<typeof presentAuthError>;

export default function KiteCallback() {
  const navigate = useNavigate();
  const revalidator = useRevalidator();
  const [searchParams] = useSearchParams();
  const [error, setError] = useState<AuthError | null>(null);

  // A request token can be exchanged exactly once; React runs effects twice
  // under StrictMode in development. Latch rather than rely on deps.
  const exchanged = useRef(false);

  useEffect(() => {
    if (exchanged.current) return;
    exchanged.current = true;

    async function complete() {
      // Scrub the token from the address bar whatever happens next.
      const requestToken = searchParams.get('request_token');
      const state = searchParams.get('state');
      const status = searchParams.get('status');
      await navigate('/settings/broker/kite/callback', { replace: true });

      if (status !== 'success') {
        setError({ message: 'Zerodha cancelled this connection.' });
        return;
      }
      if (!requestToken || !state) {
        setError({ message: 'This connection link is incomplete. Start again.' });
        return;
      }

      try {
        await broker.completeConnect(requestToken, state, 'kite');
        await navigate('/settings/broker?broker=kite&connected=1', { replace: true });
        // The connection state the terminal loader saw is stale.
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
            onClick={() => void navigate('/settings/broker?broker=kite', { replace: true })}
          >
            Back to broker settings
          </Button>
        </>
      ) : (
        <>
          <span className={s.spinner} aria-hidden="true" />
          <h1>Connecting Zerodha…</h1>
          <p>Exchanging the request token.</p>
        </>
      )}
    </div>
  );
}
