import { cx } from '$shared/ui/cx';
import { IconCheck, IconCross } from './components/icons';
import { FAQ, NEEDS, STEPS } from './content';
import s from './route.module.css';
import type { Route } from './+types/how-it-works';

export const meta: Route.MetaFunction = () => [
  { title: 'How it works · ChartNexus' },
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

        <ol className={s.timeline}>
          {STEPS.map((step) => (
            <li key={step.n} className={s.timelineItem}>
              <span className={cx(s.stepBadge, 'cn-numeric')}>{step.n}</span>
              <div className={s.timelineBody}>
                <h3>{step.title}</h3>
                <p>{step.body}</p>
              </div>
            </li>
          ))}
        </ol>
      </div>

      {/* What you need vs. what you don't — sets expectations before sign-up. */}
      <div className={s.section}>
        <div className={s.shell}>
          <div className={s.sectionHead}>
            <p className={s.eyebrow}>Before you start</p>
            <h2 className={s.h2}>What you need, and what you don’t.</h2>
          </div>

          <div className={s.checks}>
            <div className={s.checkCol}>
              <h3>What you need</h3>
              <ul className={cx(s.checkList, s.need)}>
                {NEEDS.need.map((item) => (
                  <li key={item}>
                    <IconCheck />
                    {item}
                  </li>
                ))}
              </ul>
            </div>
            <div className={s.checkCol}>
              <h3>What you don’t</h3>
              <ul className={cx(s.checkList, s.skip)}>
                {NEEDS.skip.map((item) => (
                  <li key={item}>
                    <IconCross />
                    {item}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      </div>

      {/* FAQ — plain HTML <details>, no JS, no modal. */}
      <div className={s.section}>
        <div className={s.shell}>
          <div className={s.sectionHead}>
            <p className={s.eyebrow}>Questions, answered</p>
            <h2 className={s.h2}>The honest FAQ.</h2>
            <p className={s.lead}>
              If the app polls instead of streams, this page says so. No claim here survives its
              first contradiction inside the terminal.
            </p>
          </div>

          <div className={s.faq}>
            {FAQ.map((item) => (
              <details key={item.q} className={s.faqItem}>
                <summary className={s.faqQ}>{item.q}</summary>
                <p className={s.faqA}>{item.a}</p>
              </details>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
