import { QueryClientProvider } from '@tanstack/react-query';
import { useCallback, useEffect, useRef, useState, type ComponentType } from 'react';
import { Link, Outlet, redirect, useLocation } from 'react-router';
import { currentUser } from '$contexts/identity/api';
import type { User } from '$contexts/identity/types';
import { useSignOut } from '$contexts/identity/use-session';
import { isApiError } from '$shared/api/errors';
import { createQueryClient } from '$shared/api/query-client';
import { createServerFetch } from '$shared/api/server-fetch';
import { cx } from '$shared/ui/cx';
import IconBolt from '$shared/ui/icons/IconBolt';
import IconChart from '$shared/ui/icons/IconChart';
import IconChevronDown from '$shared/ui/icons/IconChevronDown';
import IconMessage from '$shared/ui/icons/IconMessage';
import IconMoon from '$shared/ui/icons/IconMoon';
import IconSearch from '$shared/ui/icons/IconSearch';
import IconSettings from '$shared/ui/icons/IconSettings';
import IconShield from '$shared/ui/icons/IconShield';
import IconSignOut from '$shared/ui/icons/IconSignOut';
import IconSun from '$shared/ui/icons/IconSun';
import IconTarget from '$shared/ui/icons/IconTarget';
import IconUser from '$shared/ui/icons/IconUser';
import { selectIsDark, useThemeStore } from '$shared/ui/theme-store';
import { useHydratePreferences } from '$shared/ui/use-hydrate-preferences';
import { requestIdContext } from '../../middleware/context';
import FutureLabPanel from './components/FutureLabPanel';
import OptionsLabPanel from './components/OptionsLabPanel';
import s from './layout.module.css';
import type { Route } from './+types/layout';

/**
 * Gate for every terminal route — `(terminal)/+layout.ts`.
 *
 * This is a convenience redirect, not the security boundary — the API
 * authorises every request on its own. Its job is to send a signed-out visitor
 * to the sign-in page instead of showing them an empty shell full of 401s.
 */
export async function loader({ request, context }: Route.LoaderArgs) {
  // SvelteKit's load-scoped `fetch` forwarded cookies during SSR for free;
  // `createServerFetch` is what replaces that.
  const fetcher = createServerFetch(request, context.get(requestIdContext));

  try {
    return { user: await currentUser(fetcher) };
  } catch (error) {
    if (isApiError(error) && (error.status === 401 || error.status === 403)) {
      const url = new URL(request.url);
      throw redirect(`/login?next=${encodeURIComponent(url.pathname + url.search)}`, 303);
    }
    throw error;
  }
}

/**
 * SvelteKit's universal `+layout.ts` only re-ran on `invalidateAll()`. React
 * Router would otherwise re-fetch the profile on every client navigation within
 * the group, turning one `/auth/me` per document load into one per click.
 * Signing out revalidates explicitly instead.
 */
export function shouldRevalidate() {
  return false;
}

export default function TerminalLayout({ loaderData }: Route.ComponentProps) {
  // One client per browser session. Created here (not at module scope) so an
  // SSR render never shares cache across requests.
  const [queryClient] = useState(createQueryClient);

  // Adopt the persisted theme and display preferences once the browser is available.
  useHydratePreferences();

  return (
    <QueryClientProvider client={queryClient}>
      {/* The shell is a child so its hooks sit inside the provider. */}
      <TerminalShell user={loaderData.user} />
    </QueryClientProvider>
  );
}

// The menu structure the terminal will grow into. Only Dashboards and Option
// Chain resolve today; the rest are stubs the routing work will fill in.
type NavChild = {
  label: string;
  href: string;
  icon?: ComponentType;
  desc?: string;
};
type NavItem = {
  label: string;
  href: string;
  children?: NavChild[];
  menuTitle?: string;
  menuSub?: string;
  mega?: boolean;
  futureMega?: boolean;
};

const nav: NavItem[] = [
  {
    label: 'Dashboards',
    href: '/dashboard',
    menuTitle: 'Dashboards',
    menuSub: 'Live market views & analytics',
    children: [
      {
        label: 'Dashboard',
        href: '/dashboard',
        icon: IconChart,
        desc: 'Live intelligence overview'
      },
      {
        label: 'Advance Dashboard',
        href: '/advanced-dashboard',
        icon: IconTarget,
        desc: 'Deeper multi-index analytics'
      },
      { label: 'Options', href: '/options', icon: IconChart, desc: 'Chain, PCR, max pain & OI' }
    ]
  },
  { label: 'Options Lab', href: '/options/open-interest', mega: true },
  { label: 'Future Lab', href: '/future-lab', futureMega: true },
  {
    label: 'AI Console',
    href: '/ai-console',
    menuTitle: 'AI Console',
    menuSub: 'Signal analysis, the Hella agent & STRYX',
    children: [
      {
        label: 'Market Analysis',
        href: '/ai-console',
        icon: IconBolt,
        desc: 'Decision, skills, levels & trade scaffold'
      },
      {
        label: 'AI Analysis Agent',
        href: '/ai-console/agent',
        icon: IconMessage,
        desc: 'Ask Hella about the call'
      },
      {
        label: 'STRYX — Trade Calls',
        href: '/ai-console/stryx',
        icon: IconTarget,
        desc: 'Aggressive setup hunter with a defined stop'
      }
    ]
  },
  { label: 'Chart Tools', href: '/analyse' },
  { label: 'Smart Insights', href: '/smart-insights' },
  { label: 'Option Chain', href: '/option-chain' }
];

function TerminalShell({ user }: { user: User }) {
  const location = useLocation();
  const signOut = useSignOut();
  const isDark = useThemeStore(selectIsDark);
  const toggleTheme = useThemeStore((state) => state.toggle);

  const [signingOut, setSigningOut] = useState(false);

  const initials = (user.display_name || user.email || '?')
    .split(/[\s@.]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part: string) => part[0]?.toUpperCase() ?? '')
    .join('');

  const shortName = (user.display_name || user.email || 'Account').split(/[\s@]/)[0];

  // Admin Page only resolves for admins. There is no admin module yet, so it
  // points at the account root for now; gating it keeps it hidden from the
  // accounts that could not use it anyway.
  const isAdmin = user.roles.includes('admin');

  /** For the top-level tabs, where a section owns everything beneath it. */
  const isActive = (href: string): boolean =>
    location.pathname === href || location.pathname.startsWith(href + '/');

  /**
   * For the submenu entries, which are leaf destinations.
   *
   * A prefix match is wrong here: `/options/*` belongs to the Options Lab
   * mega-menu, not to the Dashboards → Options entry, so on
   * `/options/open-interest` both lit up at once. The Options Lab and Future Lab
   * panels have always matched exactly; this brings the one remaining submenu
   * into line.
   */
  const isCurrent = (href: string): boolean => location.pathname === href;

  // Native <details> menus do not close one another or dismiss on an outside
  // click. We keep the whole header in `headerEl` and close every open menu on
  // an outside click, on Escape, and after any client-side navigation so only
  // one dropdown is ever visible at a time.
  const headerEl = useRef<HTMLElement>(null);

  const closeMenus = useCallback((except?: EventTarget | null) => {
    const root = headerEl.current;
    if (!root) return;
    for (const el of root.querySelectorAll<HTMLDetailsElement>('details[open]')) {
      if (except && el.contains(except as Node)) continue;
      el.open = false;
    }
  }, []);

  useEffect(() => {
    const onPointerDown = (e: PointerEvent) => {
      if (!headerEl.current?.contains(e.target as Node)) closeMenus();
      else closeMenus(e.target);
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') closeMenus();
    };
    document.addEventListener('pointerdown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('pointerdown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [closeMenus]);

  // `afterNavigate(() => closeMenus())`.
  useEffect(() => {
    closeMenus();
  }, [location.pathname, closeMenus]);

  async function handleSignOut() {
    setSigningOut(true);
    try {
      await signOut();
    } finally {
      setSigningOut(false);
    }
  }

  return (
    <div className={s.terminal}>
      <header className={s.nav} ref={headerEl}>
        <div className={s.navLeft}>
          {/* Labelled explicitly because below 72rem the wordmark is
              `display: none` and the bolt is decorative, which left the link
              with no accessible name at all on a phone. */}
          <Link className={s.brand} to="/dashboard" aria-label="MarketCompass">
            <span className={s.mark} aria-hidden="true">
              <IconBolt />
            </span>
            <span className={s.name}>MarketCompass</span>
          </Link>

          <nav className={s.primaryNav} aria-label="Primary">
            <ul>
              {nav.map((item) => (
                <li key={item.label}>
                  {item.mega ? (
                    <details className={s.navMenu}>
                      <summary
                        className={cx(
                          s.navLink,
                          location.pathname.startsWith('/options/') && s.active
                        )}
                      >
                        {item.label}
                        <span className={s.caret} aria-hidden="true">
                          <IconChevronDown />
                        </span>
                      </summary>
                      <OptionsLabPanel />
                    </details>
                  ) : item.futureMega ? (
                    <details className={s.navMenu}>
                      <summary
                        className={cx(
                          s.navLink,
                          location.pathname.startsWith('/future-lab') && s.active
                        )}
                      >
                        {item.label}
                        <span className={s.caret} aria-hidden="true">
                          <IconChevronDown />
                        </span>
                      </summary>
                      <FutureLabPanel />
                    </details>
                  ) : item.children ? (
                    <details className={s.navMenu}>
                      <summary className={cx(s.navLink, isActive(item.href) && s.active)}>
                        {item.label}
                        <span className={s.caret} aria-hidden="true">
                          <IconChevronDown />
                        </span>
                      </summary>
                      <div className={s.submenu}>
                        {item.menuTitle ? (
                          <div className={s.submenuHead}>
                            <p className={s.submenuTitle}>{item.menuTitle}</p>
                            {item.menuSub ? <p className={s.submenuSub}>{item.menuSub}</p> : null}
                          </div>
                        ) : null}
                        {item.children.map((child) => {
                          const Icon = child.icon;
                          return (
                            <Link
                              key={child.href}
                              className={cx(s.submenuItem, isCurrent(child.href) && s.active)}
                              to={child.href}
                              prefetch="intent"
                            >
                              {Icon ? (
                                <span className={s.submenuIco} aria-hidden="true">
                                  <Icon />
                                </span>
                              ) : null}
                              <span className={s.submenuText}>
                                <span className={s.submenuLabel}>{child.label}</span>
                                {child.desc ? (
                                  <span className={s.submenuDesc}>{child.desc}</span>
                                ) : null}
                              </span>
                            </Link>
                          );
                        })}
                      </div>
                    </details>
                  ) : (
                    <Link
                      className={cx(s.navLink, isActive(item.href) && s.active)}
                      to={item.href}
                      prefetch="intent"
                    >
                      {item.label}
                    </Link>
                  )}
                </li>
              ))}
            </ul>
          </nav>
        </div>

        <div className={s.navRight}>
          <form className={s.search} role="search" onSubmit={(e) => e.preventDefault()}>
            <span className={s.searchIco} aria-hidden="true">
              <IconSearch />
            </span>
            <input
              type="search"
              placeholder="Search symbol…"
              aria-label="Search symbol"
              defaultValue="NIFTY50"
            />
          </form>

          <button
            type="button"
            className={s.iconBtn}
            onClick={() => toggleTheme()}
            aria-label={isDark ? 'Switch to light theme' : 'Switch to dark theme'}
            title="Toggle theme"
          >
            {isDark ? <IconMoon /> : <IconSun />}
          </button>

          <details className={s.account}>
            <summary aria-label="Account menu">
              <span className={s.avatar} aria-hidden="true">
                {initials}
              </span>
              <span className={s.who}>{shortName}</span>
              <span className={s.caret} aria-hidden="true">
                <IconChevronDown />
              </span>
            </summary>
            <div className={s.menu}>
              <div className={s.menuHead}>
                <span className={s.menuAvatar} aria-hidden="true">
                  {initials}
                </span>
                <div className={s.menuIdentity}>
                  <p className={s.menuName}>{user.display_name}</p>
                  <p className={s.menuEmail}>{user.email}</p>
                  <span className={s.plan}>Free plan</span>
                </div>
              </div>

              <div className={s.menuList}>
                <Link className={s.menuItem} to="/settings/profile">
                  <span className={s.menuIco} aria-hidden="true">
                    <IconUser />
                  </span>
                  Profile
                </Link>
                {isAdmin ? (
                  <Link className={s.menuItem} to="/settings">
                    <span className={s.menuIco} aria-hidden="true">
                      <IconShield />
                    </span>
                    Admin Page
                  </Link>
                ) : null}
                <Link className={s.menuItem} to="/settings/global">
                  <span className={s.menuIco} aria-hidden="true">
                    <IconSettings />
                  </span>
                  Settings
                </Link>
              </div>

              <div className={s.menuDivider} role="separator" />

              <button
                className={cx(s.menuItem, s.danger)}
                type="button"
                onClick={handleSignOut}
                disabled={signingOut}
              >
                <span className={s.menuIco} aria-hidden="true">
                  <IconSignOut />
                </span>
                {signingOut ? 'Signing out…' : 'Sign out'}
              </button>
            </div>
          </details>
        </div>
      </header>

      <main className={s.content}>
        <Outlet />
      </main>
    </div>
  );
}
