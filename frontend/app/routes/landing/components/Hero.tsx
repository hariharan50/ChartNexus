import { Link } from 'react-router';
import IconBolt from '$shared/ui/icons/IconBolt';
import { HERO, HERO_STATS } from '../copy';
import CtaLink from './CtaLink';
import PillBadge from './PillBadge';
import StatCard from './StatCard';
import s from './Hero.module.css';

interface Props {
  /** The product graphic for the right-hand column. */
  children?: React.ReactNode;
}

export default function Hero({ children }: Props) {
  return (
    <section className={s.hero}>
      <div className={s.inner}>
        <div className={s.copy}>
          {/* A sibling of the h1, not a line inside it: the badge would
              otherwise end up in the heading's accessible name. */}
          <PillBadge icon={<IconBolt />}>{HERO.eyebrow}</PillBadge>

          <h1 className={s.heading}>
            {HERO.headingLead} <strong className={s.keyword}>{HERO.headingKeyword}</strong>
          </h1>

          <p className={s.lead}>{HERO.lead}</p>

          <div className={s.actions}>
            <CtaLink to={HERO.primary.to} tone="solid" size="lg">
              {HERO.primary.label}
            </CtaLink>
            <Link className={s.secondary} to={HERO.secondary.to}>
              {HERO.secondary.label}
            </Link>
          </div>

          <p className={s.note}>{HERO.note}</p>
        </div>

        {children ? (
          <div className={s.graphic}>
            <div className={s.frame}>{children}</div>
            <div className={s.stats}>
              {HERO_STATS.map((stat) => (
                <StatCard key={stat.label} label={stat.label} value={stat.value} />
              ))}
            </div>
          </div>
        ) : null}
      </div>
    </section>
  );
}
