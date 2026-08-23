import { type ComponentType } from 'react';
import { Link, Outlet, useLocation } from 'react-router';
import { cx } from '$shared/ui/cx';
import IconAlert from '$shared/ui/icons/IconAlert';
import IconBank from '$shared/ui/icons/IconBank';
import IconBrain from '$shared/ui/icons/IconBrain';
import IconChart from '$shared/ui/icons/IconChart';
import IconChevronDown from '$shared/ui/icons/IconChevronDown';
import IconLayout from '$shared/ui/icons/IconLayout';
import IconLock from '$shared/ui/icons/IconLock';
import IconMessage from '$shared/ui/icons/IconMessage';
import IconUser from '$shared/ui/icons/IconUser';
import IconWallet from '$shared/ui/icons/IconWallet';
import s from './layout.module.css';

type NavItem = {
  label: string;
  desc: string;
  href: string;
  icon: ComponentType;
};

const nav: NavItem[] = [
  {
    label: 'Profile',
    desc: 'Your personal information',
    href: '/settings/profile',
    icon: IconUser
  },
  {
    label: 'Trading Preferences',
    desc: 'Desk defaults & display',
    href: '/settings/global',
    icon: IconChart
  },
  {
    label: 'Customization',
    desc: 'Personalize your workspace',
    href: '/settings/layout',
    icon: IconLayout
  },
  {
    label: 'Notifications',
    desc: 'In-app alerts & toasts',
    href: '/settings/notifications',
    icon: IconAlert
  },
  {
    label: 'Broker Integration',
    desc: 'Live market data via Fyers',
    href: '/settings/broker',
    icon: IconBank
  },
  {
    label: 'AI Settings',
    desc: 'LLM provider & API key',
    href: '/settings/ai',
    icon: IconBrain
  },
  {
    label: 'Power AI Agents',
    desc: 'HUGIN & MME100 automation · off by default',
    href: '/settings/power-agents',
    icon: IconBrain
  },
  {
    label: 'Account & Security',
    desc: 'Sessions & sign-out',
    href: '/settings/security',
    icon: IconLock
  },
  { label: 'My Plans', desc: 'Subscription & billing', href: '/settings', icon: IconWallet },
  { label: 'Help & Support', desc: 'Docs & contact', href: '/settings/help', icon: IconMessage }
];

export default function SettingsLayout() {
  const location = useLocation();

  function isActive(href: string): boolean {
    if (href === '/settings') return location.pathname === '/settings';
    return location.pathname === href || location.pathname.startsWith(href + '/');
  }

  return (
    <div className={s.page}>
      <header className={s.head}>
        <h1 className={s.pageTitle}>Settings</h1>
        <p className={s.pageSub}>
          Manage your profile, trading defaults, broker integration, and account controls.
        </p>
      </header>

      <div className={s.shell}>
        <nav className={s.nav} aria-label="Settings sections">
          <p className={s.navLabel}>Settings</p>
          {nav.map((item) => {
            const Icon = item.icon;
            const active = isActive(item.href);
            return (
              <Link
                key={item.href}
                className={cx(s.navItem, active && s.active)}
                to={item.href}
                prefetch="intent"
                aria-current={active ? 'page' : undefined}
              >
                <span className={s.navIco} aria-hidden="true">
                  <Icon />
                </span>
                <span className={s.navText}>
                  <span className={s.navName}>{item.label}</span>
                  <span className={s.navDesc}>{item.desc}</span>
                </span>
                <span className={s.navCaret} aria-hidden="true">
                  <IconChevronDown />
                </span>
              </Link>
            );
          })}
        </nav>

        <div className={s.content}>
          <Outlet />
        </div>
      </div>
    </div>
  );
}
