import type { ReactNode } from 'react';
import { cx } from '$shared/ui/cx';
import Pill from '../../dashboard/components/Pill';
import s from './StatTile.module.css';

type Tone = 'bullish' | 'bearish' | 'warning' | 'accent' | 'neutral';

interface Props {
  label: string;
  value: string;
  /** Small muted line under the value (e.g. "Neutral"). */
  sub?: string | undefined;
  /** A pill rendered under the value (e.g. "Dominant"). */
  pill?: string | undefined;
  pillTone?: Tone;
  /** Accent the value colour for support/resistance style tiles. */
  valueTone?: 'bullish' | 'bearish' | undefined;
  /** Optional custom footer, overrides sub/pill when provided. */
  footer?: ReactNode;
}

export default function StatTile({
  label,
  value,
  sub,
  pill,
  pillTone = 'neutral',
  valueTone,
  footer
}: Props) {
  return (
    <div className={s.tile}>
      <p className={s.label}>{label}</p>
      <p
        className={cx(
          s.value,
          'mc-numeric',
          valueTone === 'bullish' && s.bullish,
          valueTone === 'bearish' && s.bearish
        )}
      >
        {value}
      </p>
      {footer ? (
        <div className={s.footer}>{footer}</div>
      ) : pill ? (
        <div className={s.footer}>
          <Pill tone={pillTone} subtle>
            {pill}
          </Pill>
        </div>
      ) : sub ? (
        <p className={s.sub}>{sub}</p>
      ) : null}
    </div>
  );
}
