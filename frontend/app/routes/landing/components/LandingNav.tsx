import { Link } from 'react-router';
import IconBolt from '$shared/ui/icons/IconBolt';
import IconChevronDown from '$shared/ui/icons/IconChevronDown';
import IconMenu from '$shared/ui/icons/IconMenu';
import IconUser from '$shared/ui/icons/IconUser';
import { useDrawer } from '../hooks/use-drawer';
import { useMenuDismiss } from '../hooks/use-menu-dismiss';
import { NAV_LINKS, NAV_TOOLS } from '../copy';
import NavDrawer from './NavDrawer';
import s from './LandingNav.module.css';

const DRAWER_ID = 'landing-drawer';

/**
 * Two navigations, one source.
 *
 * A horizontal row above 62rem and the slide-in drawer below it. The obvious
 * hazard in that arrangement is a link that exists on desktop and quietly does
 * not on a phone, so both render from the same `NAV_LINKS` and `NAV_TOOLS`
 * arrays in `copy.ts` — adding an entry there puts it in both, and there is no
 * third place to forget.
 *
 * The dropdown is a native `<details>`, matching the terminal header. Menu
 * behaviour it does not have on its own — outside click, Escape, closing after
 * a navigation — comes from `useMenuDismiss`.
 */
export default function LandingNav() {
  const { open, setOpen, close, dialogRef, triggerRef } = useDrawer();
  const menuRoot = useMenuDismiss<HTMLDivElement>();

  return (
    <header className={s.bar}>
      <div className={s.inner}>
        <Link className={s.brand} to="/" aria-label="MarketCompass home">
          <span className={s.mark}>
            <IconBolt />
          </span>
          <span className={s.name}>MarketCompass</span>
        </Link>

        <div className={s.desktop} ref={menuRoot}>
          <nav aria-label="Primary">
            <ul className={s.links}>
              {NAV_LINKS.map((item) => (
                <li key={item.to}>
                  <Link className={s.link} to={item.to}>
                    {item.label}
                  </Link>
                </li>
              ))}
              <li>
                <details className={s.menu}>
                  <summary className={s.link}>
                    Options Lab
                    <span className={s.caret} aria-hidden="true">
                      <IconChevronDown />
                    </span>
                  </summary>
                  <ul className={s.panel}>
                    {NAV_TOOLS.map((item) => (
                      <li key={item.to}>
                        <Link className={s.panelItem} to={item.to}>
                          {item.label}
                        </Link>
                      </li>
                    ))}
                  </ul>
                </details>
              </li>
            </ul>
          </nav>

          <div className={s.actions}>
            <Link className={s.cta} to="/register">
              Create free account
            </Link>
            <Link className={s.icon} to="/login" aria-label="Sign in">
              <IconUser />
            </Link>
          </div>
        </div>

        <button
          type="button"
          ref={triggerRef}
          className={s.trigger}
          aria-label="Menu"
          aria-expanded={open}
          aria-controls={DRAWER_ID}
          onClick={() => setOpen(true)}
        >
          <IconMenu />
        </button>
      </div>

      <NavDrawer id={DRAWER_ID} onClose={close} dialogRef={dialogRef} />
    </header>
  );
}
