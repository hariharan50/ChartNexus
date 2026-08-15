import { cx } from '$shared/ui/cx';
import { SCOPE } from './content';
import s from './route.module.css';
import type { Route } from './+types/scope';

export const meta: Route.MetaFunction = () => [
  { title: 'Scope · MarketCompass' },
  {
    name: 'description',
    content:
      'The current MarketCompass scope: instruments, market data, a read-only design, and ' +
      'provenance built into every response.'
  }
];

export default function Scope() {
  return (
    <section className={s.pageIntro}>
      <div className={s.shell}>
        <div className={s.sectionHead}>
          <p className={s.eyebrow}>Current scope</p>
          <h1 className={s.h2}>What you’re actually getting.</h1>
          <p className={s.lead}>
            Read this before you sign up, not after. The current scope is Phase-1 analytics on mock
            market data by default, with Fyers integration paths for configured environments.
          </p>
        </div>

        <div className={cx(s.grid, s.grid2)}>
          {SCOPE.map((item) => (
            <article key={item.title} className={s.card}>
              <h3 className={s.plainTitle}>{item.title}</h3>
              <p className={s.cardBody}>{item.body}</p>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
