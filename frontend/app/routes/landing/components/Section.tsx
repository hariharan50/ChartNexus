import { cx } from '$shared/ui/cx';
import s from './Section.module.css';

interface Props {
  eyebrow: string;
  heading: React.ReactNode;
  lead?: string | undefined;
  /** `split` puts the visual beside the copy; `centred` puts it below. */
  variant?: 'split' | 'centred' | undefined;
  /** Visual first at wide widths. DOM order is unchanged — see the CSS. */
  reversed?: boolean | undefined;
  /** Paints the lighter charcoal band that alternates down the page. */
  panel?: boolean | undefined;
  children?: React.ReactNode;
}

/**
 * One section of the page: eyebrow → heading → lead → supporting visual.
 *
 * Every section on the page is this component, which is what keeps the vertical
 * rhythm identical without any of them agreeing on it by hand.
 */
export default function Section({
  eyebrow,
  heading,
  lead,
  variant = 'centred',
  reversed = false,
  panel = false,
  children
}: Props) {
  return (
    <section className={cx(s.section, panel && s.panel)}>
      <div className={cx(s.inner, variant === 'split' ? s.split : s.centred, reversed && s.rev)}>
        <div className={s.copy}>
          <p className={s.eyebrow}>{eyebrow}</p>
          <h2 className={s.heading}>{heading}</h2>
          {lead ? <p className={s.lead}>{lead}</p> : null}
        </div>
        {children ? <div className={s.visual}>{children}</div> : null}
      </div>
    </section>
  );
}
