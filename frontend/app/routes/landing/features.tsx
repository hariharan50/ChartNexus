import { cx } from '$shared/ui/cx';
import { Icon } from './components/icons';
import { FEATURES } from './content';
import s from './route.module.css';
import type { Route } from './+types/features';

export const meta: Route.MetaFunction = () => [
  { title: 'Features · MarketCompass' },
  {
    name: 'description',
    content:
      'Option chain, PCR & max pain, OI build-up, gamma and vega exposure, the ATM straddle, and ' +
      'provenance on every number.'
  }
];

export default function Features() {
  return (
    <section className={s.pageIntro}>
      <div className={s.shell}>
        <div className={s.sectionHead}>
          <p className={s.eyebrow}>What you get</p>
          <h1 className={s.h2}>Everything the chain says, already worked out.</h1>
          <p className={s.lead}>
            MarketCompass is built for reading NSE options — chain structure, positioning, and the
            greeks that move the premium — not for placing orders. Every module runs on mock data by
            default and labels its own provenance.
          </p>
        </div>

        <div className={cx(s.grid, s.gridFeatures)}>
          {FEATURES.map((feature) => (
            <article key={feature.title} className={s.card}>
              <span className={s.tile}>
                <Icon name={feature.glyph} />
              </span>
              <h3 className={s.cardTitle}>{feature.title}</h3>
              <p className={s.cardBody}>{feature.body}</p>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
