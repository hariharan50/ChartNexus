import type { MarketRow } from '$contexts/global-markets/types';
import { cx } from '$shared/ui/cx';
import { fmtLevel, fmtPercent, tone } from '../gia-data';
import s from './MacroStrip.module.css';

interface Props {
  markets: MarketRow[];
}

/**
 * Crude, gold, the rupee and the US ten-year.
 *
 * Not scored into the composite and not placed on the timeline — these have no
 * session an Indian open hands off from. They lead the page because they are
 * the conditions everything below was trading under: a red S&P beside a
 * spiking crude and a weak rupee is a different morning from a red S&P with
 * both of those calm, and that is context to read first rather than a footnote
 * to reach afterwards.
 */
export default function MacroStrip({ markets }: Props) {
  const rows = markets.filter((row) => row.macro);
  if (rows.length === 0) return null;

  return (
    <section className={s.wrap} aria-label="Macro context">
      {rows.map((row) => {
        const t = tone(row.change_percent);
        return (
          <div className={s.cell} key={row.key}>
            <p className={s.label}>{row.label}</p>
            <p className={cx(s.value, 'cn-numeric')}>{fmtLevel(row.price)}</p>
            <p className={cx(s.move, 'cn-numeric', s[t ?? 'none'])}>
              {fmtPercent(row.change_percent)}
            </p>
          </div>
        );
      })}
    </section>
  );
}
