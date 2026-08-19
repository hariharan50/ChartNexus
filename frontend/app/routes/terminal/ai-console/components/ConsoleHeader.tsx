import type { ReactNode } from 'react';
import { cx } from '$shared/ui/cx';
import { INSTRUMENTS } from '../ai-console-data';
import s from './ConsoleHeader.module.css';

type Props = {
  title: string;
  subtitle: ReactNode;
  instIdx: number;
  onSelect: (idx: number) => void;
  /** The brand mark letter — defaults to Hella's "H"; STRYX passes "S". */
  mark?: string;
};

/**
 * The page header the AI Console pages share — the agent's mark, the page title
 * and the NIFTY / SENSEX / BANKNIFTY switcher. Each page owns its own
 * `instIdx` state; this component only reports the selection back.
 */
export default function ConsoleHeader({ title, subtitle, instIdx, onSelect, mark = 'H' }: Props) {
  return (
    <div className={s.topbar}>
      <div className={s.brand}>
        <span className={s.brandMark}>{mark}</span>
        <div>
          <h1 className={s.title}>{title}</h1>
          <p className={s.subtitle}>{subtitle}</p>
        </div>
      </div>
      <div className={s.tabs} role="tablist" aria-label="Instrument">
        {INSTRUMENTS.map((inst, idx) => (
          <button
            key={inst.symbol}
            type="button"
            role="tab"
            aria-selected={idx === instIdx}
            className={cx(s.tab, idx === instIdx && s.active)}
            onClick={() => onSelect(idx)}
          >
            {inst.label}
          </button>
        ))}
      </div>
    </div>
  );
}
