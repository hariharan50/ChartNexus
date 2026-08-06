import { Link, Outlet, useLocation } from 'react-router';
import { cx } from '$shared/ui/cx';
import s from './layout.module.css';

const nav = [
  { label: 'Personal Info', href: '/settings/profile' },
  { label: 'Security', href: '/settings/security' },
  { label: 'Notifications', href: '/settings/notifications' },
  { label: 'Broker Connect', href: '/settings/broker' },
  { label: 'Global Settings', href: '/settings/global' },
  { label: 'My Plans', href: '/settings' },
  { label: 'Help & Support', href: '/settings/help' }
];

export default function SettingsLayout() {
  const location = useLocation();

  function isActive(href: string): boolean {
    if (href === '/settings') return location.pathname === '/settings';
    return location.pathname === href || location.pathname.startsWith(href + '/');
  }

  return (
    <div className={s.page}>
      <h1 className={s.pageTitle}>Account Settings</h1>

      <div className={s.card}>
        <nav className={s.nav} aria-label="Settings sections">
          {nav.map((item) => (
            <Link
              key={item.href}
              className={cx(s.navItem, isActive(item.href) && s.active)}
              to={item.href}
              prefetch="intent"
            >
              {item.label}
            </Link>
          ))}
        </nav>

        <div className={s.content}>
          <Outlet />
        </div>
      </div>
    </div>
  );
}
