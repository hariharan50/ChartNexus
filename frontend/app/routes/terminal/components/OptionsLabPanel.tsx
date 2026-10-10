import { Link, useLocation } from 'react-router';
import { cx } from '$shared/ui/cx';
import OptionsLabIcon from './OptionsLabIcon';
import s from './OptionsLabPanel.module.css';

interface Item {
  label: string;
  glyph: string;
  href: string;
}
interface Section {
  title: string;
  items: Item[];
}

const sections: Section[] = [
  {
    title: 'OI Tools',
    items: [
      // The raw chain every other module here derives from, so it leads the
      // list. It was a top-level tab until the header ran out of room; this is
      // where a reader looking for it would have guessed first anyway.
      { label: 'Option Chain', glyph: 'table', href: '/option-chain' },
      { label: 'Open Interest', glyph: 'layers', href: '/options/open-interest' },
      { label: 'Multi OI & Volume', glyph: 'bars', href: '/options/multi-oi-volume' },
      { label: 'Put-Call Ratio', glyph: 'scale', href: '/options/pcr' },
      { label: 'Max Pain', glyph: 'target', href: '/options/max-pain' },
      { label: 'Gamma Exposure', glyph: 'activity', href: '/options/gamma-exposure' }
    ]
  },
  {
    title: 'Popular Tools',
    items: [
      { label: 'PE-CE Difference', glyph: 'diff', href: '/options/pe-ce-difference' },
      { label: 'Timeseries', glyph: 'trend', href: '/options/timeseries' },
      { label: 'Smart OI', glyph: 'sparkle', href: '/options/smart-oi' },
      { label: 'Vega Analysis', glyph: 'flow', href: '/options/vega-analysis' }
    ]
  },
  {
    title: 'Price Tools',
    items: [
      { label: 'ATM Straddle Chart', glyph: 'straddle', href: '/options/atm-straddle' },
      { label: 'Premium Decay', glyph: 'timer', href: '/options/premium-decay' },
      { label: 'Price vs OI', glyph: 'trend', href: '/options/price-vs-oi' },
      { label: 'MultiStrike Chart', glyph: 'bars', href: '/options/multistrike' },
      { label: 'Multi-Straddle Chart', glyph: 'straddle', href: '/options/multi-straddle' }
    ]
  },
  {
    title: 'IV Tools',
    items: [
      { label: 'Volatility Skew', glyph: 'activity', href: '/options/volatility-skew' },
      { label: 'IV/HV/IVP Chart', glyph: 'trend', href: '/options/iv-hv-ivp' },
      { label: 'IV - HV', glyph: 'percent', href: '/options/iv-hv' },
      { label: 'IV Grid', glyph: 'grid', href: '/options/iv-grid' },
      { label: 'IV - Intraday', glyph: 'sigma', href: '/options/iv-intraday' }
    ]
  },
  {
    title: 'Screeners',
    items: [
      { label: 'OI Crossover', glyph: 'crossover', href: '/options/oi-crossover' },
      { label: 'Intraday Booster', glyph: 'eye', href: '/options/intraday-booster' },
      { label: 'Option Triggers', glyph: 'alert', href: '/options/option-triggers' }
    ]
  }
];

export default function OptionsLabPanel() {
  const location = useLocation();
  const isActive = (href: string) => location.pathname === href;

  return (
    <div className={s.mega}>
      <div className={s.megaHead}>
        <p className={s.megaTitle}>Options Lab</p>
        {/* Not "all modules coming soon" any more: several are built, and a
            blanket disclaimer over a working menu trains readers to ignore it. */}
        <p className={s.megaSub}>Advanced analytics toolkit · More modules landing</p>
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
