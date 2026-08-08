import { STACK } from '../copy';
import s from './StackBar.module.css';

/**
 * Where a template puts an "as seen in" row of press logos.
 *
 * MarketCompass has no press coverage, and borrowed brand marks would need a
 * remote image origin the CSP does not allow. These are the systems it actually
 * talks to, set as muted wordmarks — the same visual beat, none of the fiction.
 */
export default function StackBar() {
  return (
    <section className={s.bar} aria-label="Built on">
      <p className={s.label}>Built on</p>
      <ul className={s.list}>
        {STACK.map((name) => (
          <li key={name} className={s.item}>
            {name}
          </li>
        ))}
      </ul>
    </section>
  );
}
