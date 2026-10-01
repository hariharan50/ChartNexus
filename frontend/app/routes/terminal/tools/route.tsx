import { Link } from 'react-router';
import { TOOLS } from './catalog';
import s from './tools.module.css';
import type { Route } from './+types/route';

export const meta: Route.MetaFunction = () => [{ title: 'Tools · MarketCompass' }];

/**
 * The Tools landing — a grid of tool boxes, each opening its own page.
 *
 * This is the home for the advanced graphical tools; the boxes are placeholders
 * (B1…B12) until each one is built. The grid is driven entirely by `catalog.ts`,
 * so building a tool means editing its entry and giving it a route, not
 * rearranging this page.
 */
export default function Tools() {
  return (
    <div className={s.page}>
      <header className={s.head}>
        <h1 className={s.title}>Tools</h1>
        <p className={s.sub}>Analytical tools for options trading and market analysis</p>
      </header>

      <div className={s.grid}>
        {TOOLS.map((tool) => (
          <Link key={tool.slug} to={`/tools/${tool.slug}`} className={s.box}>
            <span className={`${s.badge} ${s[tool.tone]}`} aria-hidden="true">
              {tool.code}
            </span>
            <span className={s.boxName}>{tool.name}</span>
            <span className={s.boxDesc}>{tool.description}</span>
            <span className={s.boxOpen}>Click to open {tool.name}</span>
          </Link>
        ))}
      </div>
    </div>
  );
}
