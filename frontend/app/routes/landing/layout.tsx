import { Link, Outlet, redirect, useLocation } from 'react-router';
import { currentUser } from '$contexts/identity/api';
import { createServerFetch } from '$shared/api/server-fetch';
import IconBolt from '$shared/ui/icons/IconBolt';
import IconMenu from '$shared/ui/icons/IconMenu';
import { cx } from '$shared/ui/cx';
import { requestIdContext } from '../../middleware/context';
import { useDrawer } from './hooks/use-drawer';
import { Icon, IconClose, IconLock } from './components/icons';
import { FOOTER_COLS, NAV, SOCIAL } from './content';
import s from './route.module.css';
import type { Route } from './+types/layout';

/**
 * The chrome shared by every marketing page — nav, closing CTA, footer — with an
 * `<Outlet />` for the page body. Splitting the old single-scroll landing into a
 * page per section, this is where the parts that repeat on all of them live.
 *
 * Signed-in visitors skip the whole marketing section: they came for the
 * terminal, not the pitch, so the loader bounces them to the dashboard. The
 * redirect is on the layout so it covers Home and every sub-page alike.
 */
export async function loader({ request, context }: Route.LoaderArgs) {
  const fetcher = createServerFetch(request, context.get(requestIdContext));

  let signedIn = false;
  try {
    await currentUser(fetcher);
    signedIn = true;
  } catch {
    // Every failure renders the marketing page, not just 401/403: the front
    // door must serve even when the API is unreachable.
  }

  // Outside the `try`: redirect() throws a Response, which the catch would
  // otherwise swallow as "signed out".
  if (signedIn) throw redirect('/dashboard', 303);
  return null;
}

export default function MarketingLayout() {
  return (
    <div className={s.landing}>
      <Nav />
      <Outlet />
      <FinalCta />
      <Footer />
    </div>
  );
}

/* -- header / navbar ------------------------------------------------------ */
function Nav() {
  const { open, setOpen, close, dialogRef, triggerRef } = useDrawer();
  const { pathname } = useLocation();
  const isActive = (to: string) => (to === '/' ? pathname === '/' : pathname === to);

  return (
    <header className={s.bar}>
      <div className={cx(s.shell, s.nav)}>
        <Link className={s.brand} to="/" aria-label="MarketCompass home">
          <span className={s.mark} aria-hidden="true">
            <IconBolt />
          </span>
          MarketCompass
        </Link>

        <nav className={s.navLinks} aria-label="Primary">
          {NAV.map((item) => {
            const active = isActive(item.to);
            return (
              <Link
                key={item.to}
                className={cx(s.navLink, active && s.active)}
                to={item.to}
                aria-current={active ? 'page' : undefined}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>

        <div className={s.navActions}>
          <Link className={cx(s.btn, s.btnGhost)} to="/login">
            Log in
          </Link>
          <Link className={cx(s.btn, s.btnPrimary)} to="/register">
            Get started
          </Link>
        </div>

        <button
          type="button"
          ref={triggerRef}
          className={s.trigger}
          aria-label="Menu"
          aria-expanded={open}
          onClick={() => setOpen(true)}
        >
          <IconMenu />
        </button>
      </div>

      <dialog ref={dialogRef} className={s.drawer} aria-label="Site navigation">
        <div className={s.drawerPanel}>
          <div className={s.drawerHead}>
            <span className={s.brand}>
              <span className={s.mark} aria-hidden="true">
                <IconBolt />
              </span>
              MarketCompass
            </span>
            <button type="button" className={s.drawerClose} aria-label="Close menu" onClick={close}>
              <IconClose />
            </button>
          </div>

          <div className={s.drawerLinks}>
            {NAV.map((item) => (
              <Link key={item.to} className={s.drawerLink} to={item.to} onClick={close}>
                {isActive(item.to) ? <span className={s.drawerDot} aria-hidden="true" /> : null}
                {item.label}
              </Link>
            ))}
          </div>

          <div className={s.drawerActions}>
            <Link className={cx(s.btn, s.btnGhost)} to="/login">
              Log in
            </Link>
            <Link className={cx(s.btn, s.btnPrimary)} to="/register">
              Get started
            </Link>
          </div>
        </div>
      </dialog>
    </header>
  );
}

/* -- closing CTA (every page) --------------------------------------------- */
function FinalCta() {
  return (
    <section className={s.section}>
      <div className={s.shell}>
        <div className={s.cta}>
          <div>
            <p className={s.ctaEyebrow}>
              <IconLock />
              Read-only by design
            </p>
            <h2 className={s.ctaTitle}>Ready to read the chain with confidence?</h2>
            <p className={s.ctaBody}>
              Free, works before you connect a broker, and every number tells you where it came from
              and how old it is.
            </p>
          </div>
          <Link className={cx(s.btn, s.btnPrimary, s.btnLg)} to="/register">
            Create free account →
          </Link>
        </div>
      </div>
    </section>
  );
}

/* -- footer (warm cream) -------------------------------------------------- */
function Footer() {
  const { pathname } = useLocation();

  return (
    <footer className={s.footer}>
      <div className={s.footerInner}>
        <p className={s.footerBrand}>MarketCompass</p>

        <div className={s.footerTop}>
          {FOOTER_COLS.map((col) => (
            <div key={col.title} className={s.footerCol}>
              <p className={s.footerColTitle}>{col.title}</p>
              {col.links.map((link) => (
                <Link
                  key={link.label}
                  to={link.to}
                  className={cx(pathname === link.to && s.active)}
                  aria-current={pathname === link.to ? 'page' : undefined}
                >
                  {link.label}
                </Link>
              ))}
            </div>
          ))}

          <div className={s.footerAbout}>
            <span className={s.footerLang}>
              🌐 English
              <span className={s.footerLangCaret} aria-hidden="true">
                ▾
              </span>
            </span>
            <div className={s.footerRule} />
            <p>
              MarketCompass is a read-only NSE options analytics terminal for Indian retail traders
              — option chain, PCR, max pain, OI build-up, gamma and vega exposure and the ATM
              straddle for NIFTY, BANKNIFTY and SENSEX, each figure stamped live, cached or
              simulated.
            </p>
            <p>
              It never places an order or holds funds. The goal is to read the chain with
              confidence: know what the number is, and know where it came from.
            </p>
            <div className={s.footerSocial}>
              {SOCIAL.map((item) => (
                <a key={item.label} href="/" aria-label={item.label}>
                  <Icon name={item.glyph} />
                </a>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div className={s.footerBottom}>
        <span>
          Website made with <strong>MarketCompass</strong>
        </span>
        <span>Made with ♥ in India</span>
        <span className={s.footerBadge}>
          <Icon name="code" />
          Developed by <strong>Triecore Technologies</strong>
        </span>
      </div>
    </footer>
  );
}
