import Button from '$shared/ui/Button';
import IconArrowLeft from '$shared/ui/icons/IconArrowLeft';
import s from './forgot-password.module.css';
import type { Route } from './+types/forgot-password';

// Password reset needs an email adapter, which the backend does not have yet.
// Rather than pretend to send a message, this states the situation plainly —
// a form that silently does nothing is worse than no form.

export const meta: Route.MetaFunction = () => [{ title: 'Reset password · ChartNexus' }];

export default function ForgotPassword() {
  return (
    <>
      <header className={s.intro}>
        <h1>Reset your password</h1>
        <p>Password reset by email is not available yet.</p>
      </header>

      <div className={s.note}>
        <p>
          If you cannot sign in, contact{' '}
          <a href="mailto:support@chartnexus.app">support@chartnexus.app</a> and we will verify your
          identity and reset the account manually.
        </p>
        <p>
          If your account was created with Google, use <strong>Continue with Google</strong> on the
          sign-in page — it has no password to reset.
        </p>
      </div>

      <Button variant="secondary" full onClick={() => window.location.assign('/login')}>
        <IconArrowLeft />
        Back to sign in
      </Button>
    </>
  );
}
