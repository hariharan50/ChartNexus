import { useState, type FormEvent } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router';
import * as auth from '$contexts/identity/api';
import { presentAuthError } from '$contexts/identity/messages';
import Button from '$shared/ui/Button';
import { cx } from '$shared/ui/cx';
import IconAlert from '$shared/ui/icons/IconAlert';
import IconAt from '$shared/ui/icons/IconAt';
import IconCheck from '$shared/ui/icons/IconCheck';
import IconGoogle from '$shared/ui/icons/IconGoogle';
import PasswordField from '$shared/ui/PasswordField';
import TextField from '$shared/ui/TextField';
import s from './login.module.css';
import type { Route } from './+types/login';

export const meta: Route.MetaFunction = () => [
  { title: 'Sign in · MarketCompass' },
  { name: 'description', content: 'Sign in to your MarketCompass account.' }
];

type AuthError = ReturnType<typeof presentAuthError>;

export default function Login() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  const [identifier, setIdentifier] = useState('');
  const [password, setPassword] = useState('');
  const [rememberMe, setRememberMe] = useState(true);

  const [submitting, setSubmitting] = useState(false);
  const [googlePending, setGooglePending] = useState(false);
  const [error, setError] = useState<AuthError | null>(null);

  // Where to land after signing in. Only same-site paths are honoured, so a
  // crafted ?next= cannot bounce the user to another origin.
  const target = searchParams.get('next');
  const next = target?.startsWith('/') && !target.startsWith('//') ? target : '/dashboard';

  // Set by the register flow, which ends here rather than at the dashboard.
  const justRegistered = searchParams.get('registered') === '1';

  const fieldError = (name: string) => (error?.field === name ? error.message : undefined);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting) return;

    setSubmitting(true);
    setError(null);
    try {
      await auth.login(identifier.trim(), password);
      // The profile is no longer pushed into a store here: navigating into the
      // terminal group runs its guard loader, which fetches it.
      await navigate(next);
    } catch (caught) {
      setError(presentAuthError(caught));
      setPassword('');
    } finally {
      setSubmitting(false);
    }
  }

  async function continueWithGoogle() {
    if (googlePending) return;

    setGooglePending(true);
    setError(null);
    try {
      const { authorization_url } = await auth.startGoogleLogin(next);
      // A full navigation, not a router push: the next stop is Google's origin.
      window.location.assign(authorization_url);
    } catch (caught) {
      setError(presentAuthError(caught));
      setGooglePending(false);
    }
  }

  return (
    <>
      <header className={s.intro}>
        <h1>Welcome back</h1>
        <p>Sign in to your MarketCompass account to continue.</p>
      </header>

      {justRegistered && !error ? (
        <div className={cx(s.banner, s.success)} role="status">
          <span className={s.bannerIcon} aria-hidden="true">
            <IconCheck />
          </span>
          <div>
            <p>Account created. Sign in to continue.</p>
          </div>
        </div>
      ) : null}

      {error && !error.field ? (
        <div className={s.banner} role="alert">
          <span className={s.bannerIcon} aria-hidden="true">
            <IconAlert />
          </span>
          <div>
            <p>{error.message}</p>
            {error.action ? <Link to={error.action.href}>{error.action.label}</Link> : null}
          </div>
        </div>
      ) : null}

      <form className={s.form} onSubmit={submit} noValidate>
        <TextField
          label="Email or phone"
          value={identifier}
          onValueChange={setIdentifier}
          type="text"
          autoComplete="username"
          placeholder="you@example.com or 9876543210"
          error={fieldError('identifier') ?? fieldError('email')}
          required
          // Focusing the first field is what the Svelte page did: signing in is
          // the entire purpose of this screen.
          // eslint-disable-next-line jsx-a11y/no-autofocus
          autoFocus
          icon={<IconAt />}
        />

        <PasswordField
          value={password}
          onValueChange={setPassword}
          error={fieldError('password')}
          required
        />

        <div className={s.row}>
          <label className={s.remember}>
            <input
              type="checkbox"
              checked={rememberMe}
              onChange={(event) => setRememberMe(event.currentTarget.checked)}
            />
            <span>Remember me</span>
          </label>
          <Link className={s.mutedLink} to="/forgot-password">
            Forgot password?
          </Link>
        </div>

        <Button type="submit" full loading={submitting}>
          {submitting ? 'Signing in…' : 'Log In'}
        </Button>
      </form>

      <div className={s.divider}>
        <span>or continue with</span>
      </div>

      <Button variant="secondary" full loading={googlePending} onClick={continueWithGoogle}>
        <IconGoogle />
        Continue with Google
      </Button>

      <p className={s.footer}>
        Don&apos;t have an account? <Link to="/register">Sign up free</Link>
      </p>
    </>
  );
}
