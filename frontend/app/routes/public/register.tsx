import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router';
import * as auth from '$contexts/identity/api';
import { describePasswordPolicy, presentAuthError } from '$contexts/identity/messages';
import Button from '$shared/ui/Button';
import { cx } from '$shared/ui/cx';
import IconAlert from '$shared/ui/icons/IconAlert';
import IconAt from '$shared/ui/icons/IconAt';
import IconGoogle from '$shared/ui/icons/IconGoogle';
import IconUser from '$shared/ui/icons/IconUser';
import PasswordField from '$shared/ui/PasswordField';
import PhoneField from '$shared/ui/PhoneField';
import TextField from '$shared/ui/TextField';
import { isValidIndianMobile, toE164 } from '$shared/validation/phone';
import s from './register.module.css';
import type { Route } from './+types/register';

export const meta: Route.MetaFunction = () => [{ title: 'Create an account · ChartNexus' }];

const MIN_PASSWORD_LENGTH = 12;

type AuthError = ReturnType<typeof presentAuthError>;

export default function Register() {
  const navigate = useNavigate();

  const [displayName, setDisplayName] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');

  const [submitting, setSubmitting] = useState(false);
  const [googlePending, setGooglePending] = useState(false);
  const [error, setError] = useState<AuthError | null>(null);

  // Checked as the user types so the server never has to reject length alone.
  const tooShort = password.length > 0 && password.length < MIN_PASSWORD_LENGTH;
  // Only complain once the second field has been typed into, so the mismatch
  // does not flash while the user is still on their first keystroke.
  const mismatch = confirmPassword.length > 0 && confirmPassword !== password;
  // Same "wait until they have typed something" rule as the password mismatch.
  const phoneIncomplete = phone.length > 0 && !isValidIndianMobile(phone);
  const canSubmit =
    email.trim().length > 0 &&
    isValidIndianMobile(phone) &&
    password.length >= MIN_PASSWORD_LENGTH &&
    confirmPassword === password &&
    !submitting;

  const fieldError = (name: string) => (error?.field === name ? error.message : undefined);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmit) return;

    setSubmitting(true);
    setError(null);
    try {
      await auth.register({
        email: email.trim(),
        password,
        phone: toE164(phone),
        displayName: displayName.trim()
      });

      // Registering signs the account in, but the flow deliberately ends at the
      // sign-in page — so drop that session rather than leaving the new user
      // authenticated on a form asking them to authenticate. Sign out locally
      // even if the network call fails, then redirect.
      try {
        await auth.logout();
      } finally {
        await navigate('/login?registered=1');
      }
    } catch (caught) {
      setError(presentAuthError(caught));
    } finally {
      setSubmitting(false);
    }
  }

  async function continueWithGoogle() {
    if (googlePending) return;

    setGooglePending(true);
    setError(null);
    try {
      const { authorization_url } = await auth.startGoogleLogin('/dashboard');
      window.location.assign(authorization_url);
    } catch (caught) {
      setError(presentAuthError(caught));
      setGooglePending(false);
    }
  }

  return (
    <>
      <header className={s.intro}>
        <h1>Create your account</h1>
        <p>Start analysing NIFTY and SENSEX in minutes.</p>
      </header>

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
          label="Name"
          value={displayName}
          onValueChange={setDisplayName}
          autoComplete="name"
          placeholder="Your name"
          // Matches the Svelte page: the form is the whole screen.
          // eslint-disable-next-line jsx-a11y/no-autofocus
          autoFocus
          icon={<IconUser />}
        />

        <TextField
          label="Email"
          value={email}
          onValueChange={setEmail}
          type="email"
          inputMode="email"
          autoComplete="username"
          placeholder="you@example.com"
          error={fieldError('email')}
          required
          icon={<IconAt />}
        />

        <PhoneField
          value={phone}
          onValueChange={setPhone}
          error={
            fieldError('phone') ??
            (phoneIncomplete ? 'Enter a 10-digit Indian mobile number.' : undefined)
          }
          required
        />

        <div>
          <PasswordField
            value={password}
            onValueChange={setPassword}
            label="Password"
            placeholder="Create a password"
            autocomplete="new-password"
            error={fieldError('password')}
            required
          />
          <p className={cx(s.hint, tooShort && s.warn)}>
            {describePasswordPolicy(MIN_PASSWORD_LENGTH)}
          </p>
        </div>

        <PasswordField
          value={confirmPassword}
          onValueChange={setConfirmPassword}
          label="Confirm password"
          placeholder="Re-enter your password"
          autocomplete="new-password"
          error={mismatch ? 'Both passwords must match.' : undefined}
          required
        />

        <Button type="submit" full loading={submitting} disabled={!canSubmit}>
          {submitting ? 'Creating account…' : 'Create account'}
        </Button>
      </form>

      <div className={s.divider}>
        <span>or continue with</span>
      </div>

      <Button variant="secondary" full loading={googlePending} onClick={continueWithGoogle}>
        <IconGoogle />
        Continue with Google
      </Button>

      <p className={s.terms}>
        By creating an account you agree that ChartNexus is analytics software and does not provide
        investment advice.
      </p>

      <p className={s.footer}>
        Already have an account? <Link to="/login">Sign in</Link>
      </p>
    </>
  );
}
