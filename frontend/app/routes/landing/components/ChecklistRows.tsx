import type { ReactNode } from 'react';
import IconCheck from '$shared/ui/icons/IconCheck';
import { CHECKLIST } from '../copy';
import s from './ChecklistRows.module.css';

interface Props {
  eyebrow: string;
  heading: ReactNode;
}

export default function ChecklistRows({ eyebrow, heading }: Props) {
  return (
    <section className={s.section} aria-labelledby="checklist-heading">
      <div className={s.inner}>
        <p className={s.eyebrow}>{eyebrow}</p>
        <h2 id="checklist-heading" className={s.heading}>
          {heading}
        </h2>

        <ul className={s.grid}>
          {CHECKLIST.map((item) => (
            <li key={item.title} className={s.row}>
              <span className={s.tick} aria-hidden="true">
                <IconCheck />
              </span>
              <div className={s.text}>
                <h3 className={s.title}>{item.title}</h3>
                <p className={s.body}>{item.body}</p>
              </div>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
