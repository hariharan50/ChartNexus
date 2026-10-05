import { useEffect, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router';
import * as auth from '$contexts/identity/api';
import { presentAuthError } from '$contexts/identity/messages';
import Button from '$shared/ui/Button';
import { cx } from '$shared/ui/cx';
import IconAlert from '$shared/ui/icons/IconAlert';
import s from './google-callback.module.css';
import type { Route } from './+types/google-callback';

/**
 * Where Google returns the user (CN_GOOGLE_REDIRECT_URI).
 *
 * The `code` lands in the browser's address bar, so this page hands it
 * straight to the API and replaces the history entry — a code left in history
 * can be replayed from the back button or leaked in a referrer.
 */

export const meta: Route.MetaFunction = () => [
  { title: 'Signing in · ChartNexus' },
  { name: 'robots', content: 'noindex' }
];

type AuthError = ReturnType<typeof presentAuthError>;

export default function GoogleCallback() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [error, setError] = useState<AuthError | null>(null);

  // An authorization code can be exchanged exactly once. React runs effects
  // twice under StrictMode in development, and a remount would replay a spent
  // code as a failure, so the exchange is latched rather than merely
  // dependency-guarded.
  const exchanged = useRef(false);

  useEffect(() => {
    if (exchanged.current) return;
    exchanged.current = true;

    async function complete() {
      // The user pressed "cancel" on Google's consent screen.
      const denial = searchParams.get('error');
      if (denial) {
        setError({
          message:
            denial === 'access_denied'
              ? 'Google sign-in was cancelled.'
              : 'Google could not complete this sign-in.'
        });
        return;
      }

      const code = searchParams.get('code');
      const state = searchParams.get('state');
      if (!code || !state) {
        setError({ message: 'This sign-in link is incomplete. Start again.' });
        return;
      }

      try {
        const result = await auth.completeGoogleLogin(code, state);
        // `replace` so the back button cannot return to a spent code.
        await navigate(result.is_new_user ? '/dashboard?welcome=1' : '/dashboard', {
          replace: true
        });
      } catch (caught) {
        setError(presentAuthError(caught));
      }
    }

    void complete();
  }, [navigate, searchParams]);

  if (error) {
    return (
      <div className={s.state}>
        <span className={cx(s.icon, s.error)} aria-hidden="true">
          <IconAlert />
        </span>
        <h1>Sign-in failed</h1>
        <p>{error.message}</p>
        <Button variant="secondary" full onClick={() => void navigate('/login', { replace: true })}>
          Back to sign in
        </Button>
      </div>
    );
  }

  return (
    <div className={s.state} aria-live="polite">
      <span className={s.spinner} aria-hidden="true" />
      <h1>Signing you in…</h1>
      <p>Completing your Google sign-in.</p>
    </div>
  );
}
