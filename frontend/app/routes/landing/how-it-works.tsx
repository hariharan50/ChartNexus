import { cx } from '$shared/ui/cx';
import { STEPS } from './content';
import s from './route.module.css';
import type { Route } from './+types/how-it-works';

export const meta: Route.MetaFunction = () => [
  { title: 'How it works · MarketCompass' },
  {
    name: 'description',
    content:
      'From stranger to reading the chain in three steps: create a free account, read the ' +
      'option-chain desk, and connect a broker when ready.'
  }
];

export default function HowItWorks() {
  return (
    <section className={s.pageIntro}>
      <div className={s.shell}>
        <div className={s.sectionHead}>
          <p className={s.eyebrow}>How it works</p>
          <h1 className={s.h2}>From stranger to reading the chain in three steps.</h1>
          <p className={s.lead}>
            No setup, no card, and no broker connection to get started — mock data carries you all
            the way through, and a live feed is an optional last step.
          </p>
        </div>

        <div className={cx(s.grid, s.grid3)}>
          {STEPS.map((step) => (
            <article key={step.n} className={s.card}>
              <span className={cx(s.stepBadge, 'mc-numeric')}>{step.n}</span>
              <h3 className={s.cardTitle}>{step.title}</h3>
              <p className={s.cardBody}>{step.body}</p>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
