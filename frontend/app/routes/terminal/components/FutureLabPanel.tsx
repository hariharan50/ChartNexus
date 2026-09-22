import { Link, useLocation } from 'react-router';
import { cx } from '$shared/ui/cx';
import OptionsLabIcon from './OptionsLabIcon';
import s from './FutureLabPanel.module.css';

interface Item {
  label: string;
  glyph: string;
  href: string;
  /** Marks a recently shipped tool with the green chip. */
  isNew?: boolean;
}
interface Section {
  title: string;
  items: Item[];
}

/**
 * One flat row of titled columns, the way the Options Lab mega-menu reads.
 *
 * Analysis arrived as two more families — FII/DII and Index — and was briefly
 * a labelled band below the original two columns. Side by side is better:
 * every tool in the section is visible without the eye first parsing a
 * hierarchy, and the two Labs' menus now behave identically, which is what a
 * reader moving between them expects.
 */
const sections: Section[] = [
  {
    title: 'Price Tools',
    items: [
      { label: 'Future Dashboard', glyph: 'gauge', href: '/future-lab/dashboard' },
      { label: 'Stocks', glyph: 'layers', href: '/future-lab/stocks' },
      { label: 'Market Movers', glyph: 'trend', href: '/future-lab/market-movers' },
      { label: 'Future Heatmap', glyph: 'grid', href: '/future-lab/heatmap' }
    ]
  },
  {
    title: 'OI Tools',
    items: [{ label: 'Price vs OI', glyph: 'bars', href: '/future-lab/price-vs-oi' }]
  },
  {
    title: 'FII/DII',
    items: [
      { label: 'FII/DII Summary', glyph: 'table', href: '/future-lab/fii-dii-summary' },
      { label: 'FII/DII Cash Market', glyph: 'area', href: '/future-lab/fii-dii-cash' }
    ]
  },
  {
    title: 'Index',
    items: [
      { label: 'Index Contributors', glyph: 'columns', href: '/future-lab/index-contributors' },
      { label: 'Advance Decline', glyph: 'activity', href: '/future-lab/advance-decline' },
      { label: 'Index Weightage', glyph: 'pie', href: '/future-lab/index-weightage' },
      {
        label: 'Sector Rotation',
        glyph: 'scatter',
        href: '/future-lab/sector-rotation',
        isNew: true
      }
    ]
  }
];

export default function FutureLabPanel() {
  const location = useLocation();
  const isActive = (href: string) => location.pathname === href;

  return (
    <div className={s.mega}>
      <div className={s.megaHead}>
        <p className={s.megaTitle}>Future Lab</p>
        <p className={s.megaSub}>Futures analytics toolkit · All modules in development</p>
      </div>

      <div className={s.cols}>
        {sections.map((section) => (
          <div className={s.col} key={section.title}>
            <p className={s.colTitle}>{section.title}</p>
            <ul>
              {section.items.map((item) => (
                <li key={item.label}>
                  <Link
                    className={cx(s.item, isActive(item.href) && s.active)}
                    to={item.href}
                    prefetch="intent"
                  >
                    <span className={s.ico}>
                      <OptionsLabIcon name={item.glyph} />
                    </span>
                    <span className={s.label}>{item.label}</span>
                    {item.isNew ? (
                      <span className={s.newBadge} title="New">
                        N
                      </span>
                    ) : null}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </div>
  );
}
