import type { ReactNode } from 'react';
import { cx } from '$shared/ui/cx';
import s from './Pill.module.css';

type Tone = 'bullish' | 'bearish' | 'warning' | 'accent' | 'neutral';

interface Props {
  tone?: Tone;
  /** Softer, borderless treatment used for inline badges like ATM. */
  subtle?: boolean;
  children: ReactNode;
}

export default function Pill({ tone = 'neutral', subtle = false, children }: Props) {
  return <span className={cx(s.pill, s[tone], subtle && s.subtle)}>{children}</span>;
}
