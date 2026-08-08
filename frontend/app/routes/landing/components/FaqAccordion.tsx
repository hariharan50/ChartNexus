import type { ReactNode } from 'react';
import IconChevronDown from '$shared/ui/icons/IconChevronDown';
import { FAQ } from '../copy';
import s from './FaqAccordion.module.css';

interface Props {
  eyebrow: string;
  heading: ReactNode;
}

/**
 * `<details>`/`<summary>`, not a React-state accordion.
 *
 * The browser gives the disclosure semantics, keyboard operation and the
 * expanded state to assistive tech for free, and the rows are readable before
 * any JavaScript has run — which matters more here than on any other section,
 * because these answers are what a sceptical visitor came to read.
 */
export default function FaqAccordion({ eyebrow, heading }: Props) {
  return (
    <section className={s.section} aria-labelledby="faq-heading">
      <div className={s.inner}>
        <p className={s.eyebrow}>{eyebrow}</p>
        <h2 id="faq-heading" className={s.heading}>
          {heading}
        </h2>

        <div className={s.list}>
          {FAQ.map((item) => (
            <details key={item.q} className={s.item}>
              <summary className={s.summary}>
                <span className={s.question}>{item.q}</span>
                <span className={s.toggle} aria-hidden="true">
                  <IconChevronDown />
                </span>
              </summary>
              <p className={s.answer}>{item.a}</p>
            </details>
          ))}
        </div>
      </div>
    </section>
  );
}
