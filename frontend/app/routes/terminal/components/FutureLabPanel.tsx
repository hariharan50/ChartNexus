import { Link, useLocation } from 'react-router';
import { cx } from '$shared/ui/cx';
import OptionsLabIcon from './OptionsLabIcon';
import s from './FutureLabPanel.module.css';

interface Item {
  label: string;
  glyph: string;
  href: string;
  isNew?: boolean;
}
interface Section {
  title: string;
  items: Item[];
}

const sections: Section[] = [
  {
    title: 'Price Tools',
    items: [
      { label: 'Future Dashboard', glyph: 'gauge', href: '/future-lab/dashboard' },
      { label: 'Market Movers', glyph: 'trend', href: '/future-lab/market-movers', isNew: true },
      { label: 'Future Heatmap', glyph: 'grid', href: '/future-lab/heatmap' }
    ]
  },
  {
    title: 'OI Tools',
    items: [
      { label: 'Future Intraday', glyph: 'activity', href: '/future-lab/intraday' },
      { label: 'Price vs OI', glyph: 'bars', href: '/future-lab/price-vs-oi' },
      { label: 'Future Sentiment Cycle', glyph: 'cycle', href: '/future-lab/sentiment-cycle' }
    ]
  }
];

export default function FutureLabPanel() {
  const location = useLocation();
  const isActive = (href: string) => location.pathname === href;

  return (
    <div className={s.panel}>
      <div className={s.panelHead}>
        <p className={s.panelTitle}>Future Lab</p>
        <p className={s.panelSub}>Futures analytics toolkit · All modules in development</p>
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
                      <span className={s.newBadge} aria-label="New">
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
