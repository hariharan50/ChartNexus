import { useState } from 'react';
import { useUser } from '$contexts/identity/use-session';
import { cx } from '$shared/ui/cx';
import IconUser from '$shared/ui/icons/IconUser';
import s from './profile.module.css';
import type { Route } from './+types/profile';

export const meta: Route.MetaFunction = () => [{ title: 'Profile · Settings · ChartNexus' }];

export default function SettingsProfile() {
  const user = useUser();

  const [name, setName] = useState(user?.display_name ?? '');
  const dirty = name.trim() !== (user?.display_name ?? '');

  const initial = (user?.display_name || user?.email || '?').trim().charAt(0).toUpperCase();

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
      <header className={s.sectionHead}>
        <span className={s.sectionIco} aria-hidden="true">
          <IconUser />
        </span>
        <div>
          <h1 className={s.sectionTitle}>Profile</h1>
          <p className={s.sectionSub}>Your personal information</p>
        </div>
      </header>

      <form
        className={s.panel}
        onSubmit={(e) => {
          // No profile-update endpoint exists yet, so this only guards the
          // form; wiring persistence needs a backend PATCH /auth/me.
          e.preventDefault();
        }}
      >
        <div className={s.identity}>
          <span className={s.avatar} aria-hidden="true">
            {initial}
          </span>
          <div className={s.identityText}>
            <p className={s.identityName}>{user?.display_name || '—'}</p>
            <p className={s.identityEmail}>{user?.email || '—'}</p>
            <span className={s.tier}>Bronze Tier</span>
          </div>
        </div>

        <div className={s.fields}>
          <label className={s.field}>
            <span className={s.fieldLabel}>Full name</span>
            <input
              className={s.input}
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              autoComplete="name"
              placeholder="Your name"
            />
          </label>

          <label className={s.field}>
            <span className={s.fieldLabel}>Email address</span>
            <input
              className={cx(s.input, s.readonly)}
              type="email"
              value={user?.email ?? ''}
              readOnly
              aria-readonly="true"
            />
          </label>
        </div>

        <div className={s.actions}>
          <button className={s.save} type="submit" disabled={!dirty}>
            Save Changes
          </button>
        </div>
      </form>

      <section className={s.details}>
        <p className={s.detailsTitle}>Account details</p>

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
            <p className={s.hint}>How you authenticate into ChartNexus.</p>
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
      </section>
    </>
  );
}
