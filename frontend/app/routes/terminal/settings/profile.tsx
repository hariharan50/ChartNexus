import { useUser } from '$contexts/identity/use-session';
import { cx } from '$shared/ui/cx';
import s from './profile.module.css';
import type { Route } from './+types/profile';

export const meta: Route.MetaFunction = () => [
  { title: 'Personal Info · Settings · MarketCompass' }
];

export default function SettingsProfile() {
  const user = useUser();

  const memberSince = user?.created_at
    ? new Date(user.created_at).toLocaleDateString(undefined, {
        year: 'numeric',
        month: 'long',
        day: 'numeric'
      })
    : '—';

  const loginMethod =
    user?.linked_providers?.includes('google') && user?.has_password
      ? 'Password & Google'
      : user?.linked_providers?.includes('google')
        ? 'Google'
        : user?.has_password
          ? 'Password'
          : '—';

  return (
    <>
      <h1 className={s.title}>Personal Info</h1>

      <div className={cx(s.row, s.first)}>
        <div className={s.copy}>
          <p className={s.label}>Display name</p>
          <p className={s.hint}>The name shown across the terminal.</p>
        </div>
        <span className={s.value}>{user?.display_name || '—'}</span>
      </div>

      <div className={s.row}>
        <div className={s.copy}>
          <p className={s.label}>Email address</p>
          <p className={s.hint}>The email address associated with your account.</p>
        </div>
        <div className={s.valueStack}>
          <span className={cx(s.value, s.mono)}>{user?.email || '—'}</span>
          {user && !user.email_verified ? <span className={s.unverified}>Unverified</span> : null}
        </div>
      </div>

      <div className={s.row}>
        <div className={s.copy}>
          <p className={s.label}>Phone number</p>
          <p className={s.hint}>Also usable to sign in, alongside your email address.</p>
        </div>
        <span className={cx(s.value, s.mono)}>{user?.phone || '—'}</span>
      </div>

      <div className={s.row}>
        <div className={s.copy}>
          <p className={s.label}>Sign-in method</p>
          <p className={s.hint}>How you authenticate into MarketCompass.</p>
        </div>
        <span className={s.value}>{loginMethod}</span>
      </div>

      <div className={s.row}>
        <div className={s.copy}>
          <p className={s.label}>Member since</p>
          <p className={s.hint}>When your account was created.</p>
        </div>
        <span className={s.value}>{memberSince}</span>
      </div>

      <div className={s.row}>
        <div className={s.copy}>
          <p className={s.label}>Status</p>
          <p className={s.hint}>Your account&apos;s current standing.</p>
        </div>
        <span className={cx(s.value, s.capitalize)}>{user?.status.replace('_', ' ') || '—'}</span>
      </div>
    </>
  );
}
