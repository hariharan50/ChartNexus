import { Link } from 'react-router';
import IconBolt from '$shared/ui/icons/IconBolt';
import IconCheck from '$shared/ui/icons/IconCheck';
import { DISCLAIMER, FOOTER } from '../copy';
import s from './LandingFooter.module.css';

/**
 * No `role="contentinfo"`. `root.tsx` renders `<main id="main">` around every
 * route, so this footer is inside it — and a contentinfo landmark nested in
 * `main` is an axe violation the accessibility suite checks for. A plain
 * `<footer>` here exposes no landmark and is correct.
 */
export default function LandingFooter() {
  return (
    <footer className={s.footer}>
      <div className={s.inner}>
        <div className={s.brand}>
          <span className={s.mark}>
            <IconBolt />
          </span>
          <span className={s.name}>MarketCompass</span>
          <p className={s.tagline}>
            Options analytics for NSE indices, with provenance on every number.
          </p>
        </div>

        <div className={s.columns}>
          {FOOTER.map((column) => (
            <nav key={column.title} className={s.column} aria-label={column.title}>
              <p className={s.columnHead}>{column.title}</p>
              <ul className={s.list}>
                {column.links.map((link) => (
                  <li key={link.to}>
                    <Link className={s.link} to={link.to}>
                      <span className={s.check} aria-hidden="true">
                        <IconCheck />
                      </span>
                      {link.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </nav>
          ))}
        </div>
      </div>

      <div className={s.legal}>
        <p className={s.disclaimer}>{DISCLAIMER}</p>
        <p className={s.copy}>© {new Date().getFullYear()} MarketCompass</p>
      </div>
    </footer>
  );
}
