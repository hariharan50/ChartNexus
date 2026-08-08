import type { ReactNode } from 'react';
import IconBolt from '$shared/ui/icons/IconBolt';
import IconChart from '$shared/ui/icons/IconChart';
import IconClock from '$shared/ui/icons/IconClock';
import IconEye from '$shared/ui/icons/IconEye';
import IconLock from '$shared/ui/icons/IconLock';
import IconTarget from '$shared/ui/icons/IconTarget';
import { FEATURES } from '../copy';
import s from './FeatureGrid.module.css';

/** `copy.ts` stays plain data, so the glyph name is resolved here. */
const GLYPHS: Record<string, ReactNode> = {
  chart: <IconChart />,
  target: <IconTarget />,
  clock: <IconClock />,
  bolt: <IconBolt />,
  eye: <IconEye />,
  lock: <IconLock />
};

interface Props {
  eyebrow: string;
  heading: ReactNode;
}

export default function FeatureGrid({ eyebrow, heading }: Props) {
  return (
    <section className={s.section} aria-labelledby="features-heading">
      <div className={s.inner}>
        <p className={s.eyebrow}>{eyebrow}</p>
        <h2 id="features-heading" className={s.heading}>
          {heading}
        </h2>

        <ul className={s.grid}>
          {FEATURES.map((feature) => (
            <li key={feature.title} className={s.card}>
              <span className={s.icon} aria-hidden="true">
                {GLYPHS[feature.glyph]}
              </span>
              <div className={s.text}>
                <h3 className={s.title}>{feature.title}</h3>
                <p className={s.body}>{feature.body}</p>
              </div>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
